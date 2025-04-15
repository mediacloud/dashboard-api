"""
backend API for mediacloud dashboard
"""

# XXX TODO more data!!

import os
import urllib.parse
import time

import aiohttp
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

app = fastapi.FastAPI()

origins = [
    "*" # Accept All Origins seems fine for our usecase
]

app.add_middleware(CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
    )


GRAPHITE_HOST = urllib.parse.urlparse(os.environ["STATSD_URL"]).netloc.split(':')[0]
GRAPHITE_PORT = 81

REALM = "prod"

# create graphite stats paths
def g(path):
    return f"stats.gauges.mc.{REALM}.{path}"

def c(path):
    return f"stats.counters.mc.{REALM}.{path}"


# functions to add graphite functions to metric paths
def ss(path):
    return f"sumSeries({path})"

def asum(path, name, func="sum"):
    return f"alias(summarize({path},\"1min\",\"{func}\"),\"{name}\")"

def amax(path, name):
    return asum(path, name, "max")

GRAPHITE_METRICS = [
    # sum across all ES sub-indices, return the maximum value for each minute
    amax(ss(g("story-indexer.elastic-stats.indices.indices.primaries.docs.count.name_mc_search*")), "es_documents"),

    # Sum of requests that made it past rate limiting.
    # The web-search.cache.total counter has the fewest labels to sum up.
    asum(ss(c("web-search.cache.total.*.count")), "requests")
]

# default is from -24h until now
GRAPHITE_URL_BASE = f"http://{GRAPHITE_HOST}:{GRAPHITE_PORT}/render?format=json"
GRAPHITE_URL = "&".join([GRAPHITE_URL_BASE] + [f"target={m}" for m in GRAPHITE_METRICS])

STORIES_COUNT = 20
STORIES_URL = f"https://search.mediacloud.org/api/search/story-list?sort_order=desc&page_size={STORIES_COUNT}"
MCWEB_TOKEN = os.environ["MCWEB_TOKEN"]

DEFAULT_TTL = 60                # keep one minute

@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

def v1_zip_columns(j):
    """
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
            out.append(dp_n[i][0])
        rows.append(out)
        i += 1
    return rows

@app.get("/v1/stats")
@cache(expire=DEFAULT_TTL)
async def v1_stats_get():
    """
    NOTE! Any non-backwards-compatible change should copy this routine
    and increment the version number!
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(GRAPHITE_URL) as response:
            j = await response.json()
            resp = {
                "cols": v1_zip_columns(j)
            }
            return resp

@app.get("/v1/stories")
@cache(expire=DEFAULT_TTL)
async def v1_stories_get():
    async with aiohttp.ClientSession() as session:
        session.headers["Authorization"] = f"Token {MCWEB_TOKEN}"
        async with session.get(STORIES_URL) as response:
            j = await response.json()
            return j
