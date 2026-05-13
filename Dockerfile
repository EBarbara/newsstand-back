FROM python:3.14-slim AS builder

# Instala o uv usando o binário oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Evita a criação de arquivos .pyc e não bufferiza a saída do stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copia os arquivos de dependência primeiro para aproveitar o cache do Docker
COPY pyproject.toml uv.lock ./

# Instala as dependências usando o lockfile e sem criar venv (usando o sistema)
RUN uv sync --frozen --no-cache

# Estágio Final
FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Copia o ambiente virtual do builder
COPY --from=builder /app/.venv /app/.venv
# Copia o resto do código
COPY . .

# Expõe a porta que o Django usa
EXPOSE 8000

# Executa as migrações e sobe o servidor
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]

