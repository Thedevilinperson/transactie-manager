#!/usr/bin/with-contenv bashio
# Startscript voor de Home Assistant add-on.

export TM_DATA_DIR="/data"
export TM_PORT="8099"
export TM_HOST="0.0.0.0"

if bashio::config.has_value 'sessieduur_minuten'; then
  export TM_SESSION_MINUTES="$(bashio::config 'sessieduur_minuten')"
fi

if bashio::config.has_value 'maximale_upload_mb'; then
  export TM_MAX_UPLOAD_MB="$(bashio::config 'maximale_upload_mb')"
fi

bashio::log.info "Transactie Manager start op poort ${TM_PORT}"

cd /opt/transactie-manager
exec python3 -m waitress --host=0.0.0.0 --port="${TM_PORT}" --threads=8 wsgi:application
