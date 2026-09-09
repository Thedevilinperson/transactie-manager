ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TM_DATA_DIR=/data \
    TM_PORT=8099

# Bouwgereedschap is nodig voor cryptography en rapidfuzz op ARM.
RUN apk add --no-cache --virtual .bouw \
      build-base libffi-dev openssl-dev cargo rust python3-dev \
 && apk add --no-cache libffi openssl

WORKDIR /opt/transactie-manager

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && apk del .bouw

COPY app ./app
COPY wsgi.py start.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
CMD ["/run.sh"]
