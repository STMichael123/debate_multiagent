FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "debate_agent.app.web:app", "--host", "0.0.0.0", "--port", "8000"]
