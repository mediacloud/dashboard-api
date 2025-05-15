"""
backend API for mediacloud dashboard
"""

import os
import time
import urllib.parse
from typing import Any, TypeAlias, TypedDict, cast

# PyPI
import aiohttp
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

################ Types

JSON: TypeAlias = dict[str, Any]

V1_Response: TypeAlias = JSON | list[Any]


class V2_Response(TypedDict):
    data: JSON | list[JSON | list]
    created_ts: int


################ constants and config

# Get hostname of statsd/graphite/grafana container
# must run on same server, be linked via `dokku graphite:link OUR_APP`:
GRAPHITE_HOST = urllib.parse.urlparse(os.environ["STATSD_URL"]).netloc.split(":")[0]
GRAPHITE_PORT = 81

RENDER_URL = f"http://{GRAPHITE_HOST}:{GRAPHITE_PORT}/render"
REALM = "prod"  # stats realm to get stats for

MCWEB_TOKEN = os.environ["MCWEB_TOKEN"]

DEFAULT_TTL = 60  # cache data one minute

################ FastAPI app & initialization

app = fastapi.FastAPI()

origins = ["*"]  # Accept All Origins seems fine for our usecase

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    # all async tasks run in single thread, so use in-memory cache
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")


################ data formatting (named by version first appears in)


def maybe_round(x: float | None, digits: int) -> float | None:
    if x is None:
        return x
    return round(x, digits)


def v1_zip_columns(j: list[JSON]) -> list[list[Any]]:
    """
    take data from graphite:
    return list where first row is column names,
    followed by rows with values for each column
    (more compact than list of dicts)
    """
    headers = ["ts"]
    for metric in j:
        headers.append(metric["target"])

    rows = [headers]

    # list of lists of [value, ts]
    datapoints = [col["datapoints"] for col in j]

    # for now, assume that metrics
    # come with an indentical series of timestamps
    # if not, need to track index for each column separately!
    i = 0
    for metric0 in datapoints[0]:
        value0 = metric0[0]
        ts0 = time.strftime("%Y-%m-%d %H:%M", time.gmtime(metric0[1]))
        out = [ts0, value0]
        # loop for remaining columns
        for dp_n in datapoints[1:]:
            out.append(maybe_round(dp_n[i][0], 1))
        rows.append(out)
        i += 1
    return rows


def v2_wrap(data: JSON | list[Any]) -> V2_Response:
    """
    standard wrapper for v2 of API
    """
    return {"data": data, "created_ts": int(time.time())}


################ stats endpoint


# create graphite stats paths
def g(path: str) -> str:
    return f"stats.gauges.mc.{REALM}.{path}"


def c(path: str) -> str:
    return f"stats.counters.mc.{REALM}.{path}"


def t(path: str) -> str:
    return f"stats.timers.mc.{REALM}.{path}"


# functions to add graphite functions to metric paths
def ss(path: str) -> str:
    """sum (wildcard) series path into one series"""
    return f"sumSeries({path})"


def asum(path: str, name: str, func: str = "sum") -> str:
    """
    summarize samples for each minute (using `func`: default sum)
    and apply an alias
    """
    return f'alias(summarize({path},"1min","{func}"),"{name}")'


def amax(path: str, name: str) -> str:
    """
    get maximum sample for each minute, and apply an alias
    """
    return asum(path, name, "max")


def amedian(path: str, name: str) -> str:
    """
    get median sample for each minute, and apply an alias
    """
    return asum(path, name, "median")


####
# list of metrics for "stats" endpoint to return
# MUST include an alias name!

GRAPHITE_METRICS: list[str] = [
    # sum across all ES sub-indices, return the maximum value for each minute
    amax(
        ss(
            g(
                "story-indexer.elastic-stats.indices.indices.primaries.docs.count.name_mc_search*"
            )
        ),
        "es_documents",
    ),
    # sum total requests served each minute by gunicorn, regardless of status
    asum(c("web-search.gunicorn.requests.count"), "requests"),
    # Max working feeds (fetched and successfully parsed document in
    # last 24 hrs regardless of whether there were new stories found)
    amax(
        g("rss-fetcher.rss-fetcher-stats.feeds.recent.hours_24.status_working"),
        "feeds_working",
    ),
    # median "college" count-over-time
    amedian(
        t("web-search.monitor-api.college.31d.count-over-time.median"),
        "median_search_ms",
    ),
    # sum of successful document fetches per minute
    asum(t("rss-fetcher.fetcher.total.status_SUCC.count"), "feed_docs_fetched"),
]

# default is from -24h until now
GRAPHITE_PARAMS = "&".join(f"target={m}" for m in GRAPHITE_METRICS)
GRAPHITE_URL = f"{RENDER_URL}?format=json&{GRAPHITE_PARAMS}"


# original development version: remove soon!
@app.get("/v1/stats")
@cache(expire=DEFAULT_TTL)
async def v1_stats_get() -> V1_Response:
    """
    DEPRECATED: DO NOT USE!
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(GRAPHITE_URL) as response:
            j = await response.json()
            resp = {"cols": v1_zip_columns(j)}
            return resp


@app.get("/v2/stats")
@cache(expire=DEFAULT_TTL)
async def v2_stats_get() -> V2_Response:
    """
    NOTE! Any non-backwards-compatible change should copy this routine
    and increment the version number!

    v2: uses v2_wrap()
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(GRAPHITE_URL) as response:
            j = await response.json()
            return v2_wrap(v1_zip_columns(j))


################ stories endpoint: return recent stories

#### original development version: remove soon!

STORIES_COUNT = 20
STORIES_URL = f"https://search.mediacloud.org/api/search/story-list?sort_order=desc&page_size={STORIES_COUNT}"


@app.get("/v1/stories")
@cache(expire=DEFAULT_TTL)
async def v1_stories_get() -> V1_Response:
    """
    DEPRECATED
    """
    async with aiohttp.ClientSession() as session:
        session.headers["Authorization"] = f"Token {MCWEB_TOKEN}"
        async with session.get(STORIES_URL) as response:
            return cast(V1_Response, await response.json())


#### version 2; use random sample

SAMPLE_URL = "https://search.mediacloud.org/api/search/sample"


@app.get("/v2/stories")
@cache(expire=DEFAULT_TTL)
async def v2_stories_get() -> V2_Response:
    """
    returns random sample from last 24 hours, to try to show
    representative stories (last 20 may all be from same source)
    """
    async with aiohttp.ClientSession() as session:
        session.headers["Authorization"] = f"Token {MCWEB_TOKEN}"
        now = time.time()
        start = time.strftime("%Y-%m-%d", time.gmtime(now - 24 * 60 * 60))
        end = time.strftime("%Y-%m-%d", time.gmtime(now))
        # doesn't (currently) take count parameter!
        url = f"{SAMPLE_URL}?start={start}&end={end}"
        async with session.get(url) as response:
            j = await response.json()
            # perhaps trim any unwanted columns?
            return v2_wrap(j["sample"])
