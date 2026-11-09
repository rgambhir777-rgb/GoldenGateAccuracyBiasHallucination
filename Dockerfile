# GoldenGate: API and dashboard in one container. Runs offline with no API keys.
#   docker run --rm -p 127.0.0.1:8000:8000 <image>   then open http://localhost:8000
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    GOLDENGATE_WORKSPACE=/data

WORKDIR /app

# Dependencies first so code changes do not reinstall them. Only the runtime
# dependencies from pyproject.toml, pinned by the lock file (no pytest/pyinstaller).
COPY pyproject.toml requirements-lock.txt ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt -c requirements-lock.txt \
    && rm /tmp/requirements.txt

# Code and read-only resources. The package runs from /app, so /app is the resource root.
COPY goldengate/ goldengate/
COPY corpus/ corpus/
COPY golden/ golden/
COPY rubrics/ rubrics/
COPY gates.yaml ./
COPY frontend/dist/ frontend/dist/

# Run unprivileged. All writable state (database, runs, reports, .env, editable
# golden sets and gates) lives in /data. The demo releases are seeded at build time
# so the container serves the dashboard within seconds of starting.
RUN useradd --create-home --uid 1000 goldengate \
    && mkdir /data \
    && chown goldengate:goldengate /data
USER goldengate
RUN python -m goldengate demo
VOLUME /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

CMD ["python", "-m", "goldengate", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-open"]
