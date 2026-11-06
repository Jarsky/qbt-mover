FROM alpine:3.24

RUN echo "@testing https://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories \
    && apk add --no-cache \
        dcron \
        openssh-client \
        python3 \
        tzdata \
        qbittorrent-cli@testing

WORKDIR /app

COPY src/qbt_mover/ /app/qbt_mover/
COPY config/config.ini.example /app/defaults/config.ini
COPY --chmod=755 docker/entrypoint.sh /app/entrypoint.sh
COPY --chmod=755 docker/askpass.sh /usr/local/libexec/qbt-mover-askpass
COPY --chmod=755 docker/qbt-mover.sh /usr/local/bin/qbt-mover

HEALTHCHECK --interval=1m --timeout=5s CMD ["pgrep", "crond"]

CMD ["/app/entrypoint.sh"]
