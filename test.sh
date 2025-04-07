#!/bin/sh

# run server outside dokku

IP=$(ssh dokku@$(hostname -f) graphite:info ObscureStatsServiceName --internal-ip)
export STATSD_URL=statsd://$IP:8125
export PATH=`pwd`/venv/bin:$PATH
export PORT=54321
./run.sh


