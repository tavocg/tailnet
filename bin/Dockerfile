FROM rust:1-alpine AS builder

ARG BIN_GIT_REF=master

RUN apk add --no-cache git musl-dev

WORKDIR /src
RUN git clone https://github.com/w4/bin.git bin && \
    cd bin && \
    git checkout "${BIN_GIT_REF}" && \
    cargo build --release && \
    chown nobody:nogroup target/release/bin

FROM scratch

COPY --from=builder /src/bin/target/release/bin /usr/local/bin/bin
COPY --from=builder /etc/passwd /etc/passwd

USER nobody
ENTRYPOINT ["/usr/local/bin/bin"]
