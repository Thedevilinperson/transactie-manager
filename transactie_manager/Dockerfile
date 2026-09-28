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

# Alleen kant-en-klare pakketten (wheels). Voor Python 3.13 op Alpine (musl)
# bestaan die voor elk pakket, zowel voor amd64 als voor aarch64.
#
# Tot versie 0.33.2 viel dit bij de minste fout terug op compileren: Rust,
# Cargo en een C-compiler installeren en alles uit de broncode bouwen. Een
# kleine haper in het netwerk tijdens het downloaden volstond om daarin te
# belanden, en dat compileren duurt langer dan de 15 minuten die de Supervisor
# een bouw gunt ("Timeout starting app_builder"). Nu mislukt een download snel
# en met een duidelijke melding, en probeert pip het eerst zelf opnieuw.
# pip wordt ook niet meer eerst bijgewerkt: dat was een extra download die
# niets bijbracht.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=30 \
    PIP_RETRIES=5 \
    PIP_PROGRESS_BAR=off

RUN pip install --only-binary=:all: -r requirements.txt

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
