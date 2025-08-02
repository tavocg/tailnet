FROM debian:bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN git clone https://git.swurl.xyz/swirl/clink.git /tmp/clink && \
    make -C /tmp/clink && make -C /tmp/clink install-bin && \
    rm -rf /tmp/clink

RUN mkdir /clink-data

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
