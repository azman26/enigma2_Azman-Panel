ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git binutils tar gzip xz-utils \
    && git clone --depth 1 https://git.yoctoproject.org/opkg-utils /tmp/opkg-utils \
    && cp /tmp/opkg-utils/opkg-build /usr/local/bin/opkg-build \
    && chmod 0755 /usr/local/bin/opkg-build \
    && rm -rf /tmp/opkg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY build_ipk.sh /build/build_ipk.sh
RUN chmod +x /build/build_ipk.sh

ENTRYPOINT ["/build/build_ipk.sh"]
