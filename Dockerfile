FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY config.yaml ./config.yaml

RUN mkdir -p logs

CMD ["uv", "run", "python", "-m", "app.main"]
