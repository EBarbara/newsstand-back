FROM python:3.14-slim

# Evita a criação de arquivos .pyc e não bufferiza a saída do stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala o uv (gerenciador de pacotes moderno)
RUN pip install uv

# Copia os arquivos de dependência primeiro para aproveitar o cache do Docker
COPY pyproject.toml uv.lock ./

# Instala as dependências no sistema
RUN uv pip install --system -r pyproject.toml

# Copia o resto do código
COPY . .

# Expõe a porta que o Django usa
EXPOSE 8000

# Executa as migrações e sobe o servidor
# Em um ambiente 100% produtivo, o ideal é usar gunicorn ou uvicorn.
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
