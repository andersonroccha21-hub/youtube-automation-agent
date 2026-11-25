FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml main.py ./
COPY pipeline ./pipeline
COPY skills ./skills
COPY web ./web
COPY channels ./channels
RUN useradd --create-home --uid 10001 pipeline && mkdir /app/runs \
    && chown pipeline:pipeline /app/runs
USER pipeline
ENTRYPOINT ["python", "main.py"]
CMD ["--channel", "channels/canal_exemplo/config.yaml"]
