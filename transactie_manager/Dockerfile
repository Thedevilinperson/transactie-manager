# Het basisimage staat hier rechtstreeks, niet meer in build.yaml. Home Assistant
# publiceert deze images als multi-platform manifest, dus één regel volstaat voor
# alle architecturen; Docker kiest de juiste variant bij het bouwen.
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.22

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TM_DATA_DIR=/data \
    TM_PORT=8099 \
    TM_HOST=0.0.0.0

WORKDIR /opt/transactie-manager

COPY requirements.txt ./

# Eerst kant-en-klare pakketten proberen. Bestaan die voor deze architectuur,
# dan is bouwgereedschap niet nodig en scheelt dat een flink stuk bouwtijd.
RUN set -eux; \
    pip install --no-cache-dir --upgrade pip; \
    if ! pip install --no-cache-dir --only-binary=:all: -r requirements.txt; then \
        apk add --no-cache --virtual .bouw \
            build-base libffi-dev openssl-dev cargo rust python3-dev; \
        apk add --no-cache libffi openssl libstdc++; \
        pip install --no-cache-dir -r requirements.txt; \
        apk del .bouw; \
    fi

COPY app ./app
# De handleiding wordt in de toepassing zelf getoond, dus ze moet mee.
COPY docs ./docs
COPY wsgi.py start.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
    org.opencontainers.image.title="Transactie Manager" \
    org.opencontainers.image.description="Huishoudboekje op basis van bankafschriften" \
    org.opencontainers.image.source="https://github.com/GEBRUIKERSNAAM/transactie-manager" \
    org.opencontainers.image.licenses="MIT"

EXPOSE 8099
CMD ["/run.sh"]
