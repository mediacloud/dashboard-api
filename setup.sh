#!/bin/sh

# TEMP SETUP SCRIPT!!!!!!

APP_NAME=dashboard-api
STATS_SERVICE=ObscureStatsServiceName
DOMAIN=$APP_NAME.mediacloud.org

if ! grep -sq '^export MCWEB_TOKEN=' key.sh ; then
    # XXX use a private config repo???
    echo 'Need key.sh with MCWEB_TOKEN' 1>&2
    exit 1
fi
. ./key.sh

# XXX check first!
dokku apps:create $APP_NAME
dokku graphite:link $STATS_SERVICE $APP_NAME

dokku config:set $APP_NAME MCWEB_TOKEN=$MCWEB_TOKEN

dokku domains:add $APP $DOMAIN
dokku letsencrypt:enable $APP

git remote add dokku dokku@tarbell:$APP_NAME
