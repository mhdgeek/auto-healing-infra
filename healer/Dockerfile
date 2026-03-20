FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
RUN groupadd -r healer && useradd -r -g healer healer
WORKDIR /app
COPY --from=builder /install /usr/local
COPY healer.py .
RUN chown -R healer:healer /app

ENV PORT=8000
USER healer
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "60", "--access-logfile", "-", "healer:app"]
