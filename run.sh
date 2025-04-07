#!/bin/sh

# expects MCWEB_TOKEN, STATSD_URL, PORT

# run server under dokku
uvicorn \
    --host 0.0.0.0 \
    --port $PORT \
    api:app
