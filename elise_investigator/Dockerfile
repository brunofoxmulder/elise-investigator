FROM ghcr.io/home-assistant/base:3.23

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache python3 py3-aiohttp

COPY app /app
COPY run.sh /run.sh
RUN chmod 0755 /run.sh

# Make the application directory explicit for Python imports at runtime.
WORKDIR /app
ENV PYTHONPATH=/app

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="Élise Investigator" \
  org.opencontainers.image.description="Read-only causal investigator for Home Assistant"

CMD ["/run.sh"]
