FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY ops_copilot ./ops_copilot
COPY scripts ./scripts
COPY db ./db

RUN pip install --no-cache-dir .

ENV DATA_FILE=/app/data/Sistema\ de\ Análisis\ Inteligente\ para\ Operaciones\ Rappi\ -\ Dummy\ Data\ \(2\)\ \(1\)\ \(3\)\ \(1\)\ \(1\)\ \(1\)\ \(1\)\ \(1\)\ \(2\).xlsx

EXPOSE 8000

CMD ["uvicorn", "ops_copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]

