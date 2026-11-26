# SafeFix sandbox execution image.
#
# This image is used by the Docker execution backend for UNTRUSTED test
# commands (see safefix/runtime/docker_executor.py). It pre-installs pytest so
# tasks do not need a networked preparation stage.
#
# Build:  docker build -t safefix-sandbox:latest .
# Use:    configure SandboxLimits(image="safefix-sandbox:latest")
#
# Hardening applied at `docker run` time by the executor: non-root uid 1000,
# --cap-drop ALL, --security-opt no-new-privileges, --network none,
# CPU/memory/pids limits, only the task workspace mounted, --rm cleanup.

FROM python:3.12-slim

RUN pip install --no-cache-dir pytest \
    && useradd -m -u 1000 safefix

USER safefix
WORKDIR /work

CMD ["python", "-m", "pytest", "-q"]