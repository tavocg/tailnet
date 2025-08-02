FROM debian:bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN git clone https://git.swurl.xyz/swirl/pacebin.git /tmp/pacebin && \
    make -C /tmp/pacebin && make -C /tmp/pacebin install-bin && \
    rm -rf /tmp/pacebin

RUN mkdir /pacebin-data

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
