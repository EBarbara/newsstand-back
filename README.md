# Newsstand Backend

Back-end da aplicação Newsstand, responsável por fornecer a API RESTful de revistas, edições e capas para o front-end. Desenvolvido com **Django**, **Django REST Framework** e gerenciado via **uv**.

## 🛠️ Tecnologias Principais
* Python 3.14+
* Django 6.0+
* Django REST Framework
* SQLite
* uv (Package Manager)

## 💻 Desenvolvimento Local

O projeto utiliza o `uv` para um gerenciamento de dependências extremamente rápido.

1. Instale o [uv](https://github.com/astral-sh/uv) na sua máquina (ex: `pip install uv`).
2. Sincronize as dependências e crie o ambiente virtual:
   ```bash
   uv sync
   ```
3. Execute as migrações do banco de dados:
   ```bash
   uv run python manage.py migrate
   ```
4. Inicie o servidor de desenvolvimento:
   ```bash
   uv run python manage.py runserver
   ```
A API estará acessível em `http://localhost:8000`.

## 🚀 Deploy (Docker & GitHub Actions)

Este projeto está configurado com um pipeline moderno de CI/CD para Docker.

Ao realizar um `push` na branch `main` ou `master`, o GitHub Actions (ver `.github/workflows/docker-publish.yml`) automaticamente cria a imagem Docker otimizada e a publica no **GitHub Container Registry (GHCR)**.

### Para rodar a versão de produção (via docker-compose):
Basta usar o orquestrador configurado passando a imagem compilada:
```yaml
services:
  backend:
    image: ghcr.io/SEU_USUARIO/newsstand-back:latest
    ports:
      - "8000:8000"
    volumes:
      - ./db.sqlite3:/app/db.sqlite3
      - ./media:/app/media
```

## 📜 Licença
Distribuído sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
