FROM python:3.12-alpine

WORKDIR /app
COPY server/content_store.py server/server.py ./
COPY docs/content.json ./seed/content.json

RUN addgroup -S -g 10001 academy && adduser -S -D -H -u 10001 -G academy academy \
    && mkdir -p /data && chown -R academy:academy /data /app

USER academy
EXPOSE 8080
CMD ["python", "-u", "server.py"]
