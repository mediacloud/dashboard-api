#!/bin/sh

# run server outside dokku on tarbell

if [ $(hostname) != tarbell.angwin ]; then
    echo must be run on tarbell for access to statsd 1>&2
    exit 1
fi
IP=$(ssh dokku@$(hostname -f) graphite:info ObscureStatsServiceName --internal-ip)
export STATSD_URL=statsd://$IP:8125
export PATH=`pwd`/venv/bin:$PATH
export PORT=54321
./run.sh
