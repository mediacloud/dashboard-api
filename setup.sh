#!/bin/sh

# TEMP SETUP SCRIPT!!!!!!

APP_NAME=dashboard-api
STATS_SERVICE=ObscureStatsServiceName

# XXX check first!
dokku apps:create $APP_NAME
dokku graphite:link $STATS_SERVICE $APP_NAME

source key.sh
dokku config:set $APP_NAME MCWEB_TOKEN=$MCWEB_TOKEN

git remote add dokku dokku@tarbell:$APP_NAME
