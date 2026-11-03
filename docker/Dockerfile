# Pin the multi-architecture manifest, not a mutable Python image tag.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

ARG TARGETARCH
ARG DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
ARG AWSCLI_VERSION=2.39.0
# SHA-256 digests from the official AWS CLI v2 release archives.
ARG AWSCLI_X86_64_SHA256=6c89ce7ed7bc0a2520e2bc3eeedfea4e2eb2e7da2836860c9471871408404036
ARG AWSCLI_AARCH64_SHA256=05da9395b4d148c42e959192650bf4a7cbb59ea275fa334d0936c593c27b946f

RUN set -eux; \
    case "${TARGETARCH:?Docker BuildKit must provide TARGETARCH}" in \
        amd64) aws_arch="x86_64"; aws_sha256="${AWSCLI_X86_64_SHA256}" ;; \
        arm64) aws_arch="aarch64"; aws_sha256="${AWSCLI_AARCH64_SHA256}" ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    case "${DEBIAN_MIRROR}" in https://*|http://*) ;; *) echo "invalid DEBIAN_MIRROR" >&2; exit 1 ;; esac; \
    case "${DEBIAN_SECURITY_MIRROR}" in https://*|http://*) ;; *) echo "invalid DEBIAN_SECURITY_MIRROR" >&2; exit 1 ;; esac; \
    sed -i \
      -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
      -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install --no-install-recommends --yes ca-certificates curl tzdata unzip; \
    curl --fail --location --show-error --silent \
      "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}-${AWSCLI_VERSION}.zip" \
      --output /tmp/awscliv2.zip; \
    echo "${aws_sha256}  /tmp/awscliv2.zip" | sha256sum --check --status; \
    unzip -q /tmp/awscliv2.zip -d /tmp; \
    /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli; \
    aws --version; \
    rm -rf /tmp/aws /tmp/awscliv2.zip; \
    apt-get purge --auto-remove --yes curl unzip; \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 kiro \
    && useradd --uid 10001 --gid kiro --create-home --home-dir /home/kiro \
      --shell /usr/sbin/nologin kiro

WORKDIR /app

COPY app/ /app/app/
COPY web/ /app/web/

RUN chmod --recursive a=rX /app

ENV HOME=/home/kiro \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

USER 10001:10001

CMD ["python", "-m", "app.server", "--config", "/app/config.local.toml"]
