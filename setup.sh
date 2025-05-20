#!/bin/sh

if [ $(whoami) = root ]; then
    echo run as regular user 1>&2
    exit 1
fi

INSTANCE=$1
FQDN=$(hostname -f | tr A-Z a-z)
APP_NAME=vitals-api
BASE_DOMAIN=mediacloud.org
case $INSTANCE in
prod)
    DOMAIN=$APP_NAME.$BASE_DOMAIN
    ;;
staging)
    APP_NAME=staging-$APP_NAME
    DOMAIN=$APP_NAME.$(hostname -s).$BASE_DOMAIN
    ;;
*)
    echo 'Usage: setup.sh prod|staging' 1>&2
    exit 1
    ;;
esac

GIT_REMOTE=dokku_$INSTANCE

# subterfuge for wrapping in letsencrypt:
STATS_SERVICE=ObscureStatsServiceName

# not needed if root:
dokku() {
    ssh dokku@$FQDN $*
}

if ! grep -sq '^export MCWEB_TOKEN=' key.sh ; then
    # XXX use a private config repo???
    echo 'Need key.sh with MCWEB_TOKEN' 1>&2
    exit 1
fi
. ./key.sh

if dokku graphite:exists $STATS_SERVICE >/dev/null 2>&1; then
    echo found dokku graphite service $STATS_SERVICE
else
    echo could not find dokku graphite service $STATS_SERVICE 1>&2
    exit 1
fi

if dokku apps:exists $APP_NAME >/dev/null 2>&1; then
    echo found dokku app $APP_NAME
else
    echo creating dokku app $APP_NAME
    if ! dokku apps:create $APP_NAME; then
	echo dokku apps:create $APP_NAME failed 1>&2
	exit 1
    fi
fi

if dokku graphite:linked $STATS_SERVICE $APP_NAME >/dev/null 2>&1; then
   echo app $APP_NAME linked to graphite service $STATS_SERVICE
else
   echo linking app $APP_NAME to graphite service $STATS_SERVICE
   if ! dokku graphite:link $STATS_SERVICE $APP_NAME; then
       echo dokku graphite:link $STATS_SERVICE $APP_NAME failed 1>&2
       exit 1
   fi

fi

# XXX check first??
if dokku config:show $APP_NAME | grep "MCWEB_TOKEN:[ 	]*$MCWEB_TOKEN" >/dev/null; then
    echo config OK
else
    dokku config:set --no-restart $APP_NAME MCWEB_TOKEN=$MCWEB_TOKEN
fi

CURR_DOMAINS=$(dokku domains:report $APP_NAME | grep '^ *Domains app vhosts:' | sed -e 's/^.*: */ /' -e 's/$/ /')
if echo "$CURR_DOMAINS" | fgrep " $DOMAIN " >/dev/null; then
    echo app domain $DOMAIN is set
else
    dokku domains:add $APP_NAME $DOMAIN
fi

if dokku letsencrypt:active $APP_NAME >/dev/null 2>&1; then
    echo letsencrypt active for $APP_NAME
else
    echo enabling letsencrypt for $APP_NAME
    if ! dokku letsencrypt:enable $APP_NAME; then
	echo dokku letsencrypt:enable $APP_NAME failed 1>&2
	exit 1
    fi
fi

if git remote | grep $GIT_REMOTE >/dev/null; then
    echo found git remote $GIT_REMOTE
else
    echo adding git remote $GIT_REMOTE
    if ! git remote add $GIT_REMOTE dokku@$FQDN:$APP_NAME; then
	echo git remote add $GIT_REMOTE failed 1>&2
	exit 1
    fi
fi
