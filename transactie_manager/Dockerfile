# Home Assistant vult BUILD_FROM in vanuit build.yaml. De waarde hieronder is
# enkel de terugval wanneer je het beeld met de hand bouwt.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.22
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TM_DATA_DIR=/data \
    TM_PORT=8099 \
    TM_HOST=0.0.0.0

WORKDIR /opt/transactie-manager

COPY requirements.txt ./

# Voor amd64 en aarch64 bestaan er kant-en-klare musl-wheels; dan is de
# omweg via bouwgereedschap niet nodig. Op armv7 moet cryptography wel
# gecompileerd worden, en daarvoor zijn Rust en de headers vereist.
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
COPY wsgi.py start.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
CMD ["/run.sh"]
