# airflow/Dockerfile — Airflow image + docker CLI so the scheduler can
# `docker exec` into the pension-app container via the mounted host socket (A-1).
FROM apache/airflow:3.2.2

USER root
# Install the Docker CLI from Docker's official apt repo (NOT Debian's docker.io,
# whose CLI is too old — speaks API 1.41, but Docker Desktop's daemon needs >=1.44).
# We install only the CLI (docker-ce-cli); no daemon runs here. We use it purely
# to `docker exec` against the host daemon via the mounted socket.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
# Compose runs this container as `user: root`, so no need to switch back.