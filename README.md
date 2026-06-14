# Short Video Generation Platform

A Docker-first SaaS application for creating promotional short videos. The
project combines a React client, a FastAPI backend, PostgreSQL, Redis, Celery,
and S3-compatible object storage for prompt planning, storyboard generation,
media asset handling, and asynchronous video generation workflows.

## Features

- Prompt-based promotional video project creation
- Storyboard generation and editing before production starts
- Scene-level video generation, retry, cancel, and progress tracking
- User authentication with client and backoffice API surfaces
- S3-compatible media storage through AWS S3 or local MinIO
- Background processing with Celery workers and scheduled jobs
- Docker Compose deployment for frontend, backend, database, Redis, MinIO, and
  workers

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Ant Design, Zustand |
| Backend | FastAPI, SQLAlchemy async ORM, Pydantic |
| Database | PostgreSQL |
| Cache and Queue | Redis |
| Background Jobs | Celery worker and Celery beat |
| Object Storage | AWS S3-compatible storage, MinIO for local development |
| Deployment | Docker Compose |

## Project Structure

```text
.
+-- backend/                 # FastAPI application, migrations, workers, tests
+-- frontend/                # React + Vite frontend application
+-- docker-compose.yml       # Production-style service topology
+-- docker-compose.dev.yml   # Development overrides with hot reload
+-- deploy.sh                # Unified development and operations helper
+-- .env.example             # Root environment template
`-- README.md
```

## Prerequisites

- Docker and Docker Compose
- Git
- pnpm, only when running frontend tooling outside Docker
- Python virtual environment, only when running backend tooling outside Docker

## Quick Start

1. Create the local environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` locally with your own development values. Keep real secrets out
   of Git.

3. Start the development stack:

   ```bash
   ./deploy.sh dev
   ```

4. Open the application:

   - Frontend: `http://localhost:3000`
   - Backend API: `http://localhost:${API_PORT}`
   - Client API docs: `http://localhost:${API_PORT}/client/docs`
   - Backoffice API docs: `http://localhost:${API_PORT}/backoffice/docs`
   - MinIO console: `http://localhost:9001`

`API_PORT` comes from the root `.env` file and defaults to the value configured
in Docker Compose when omitted.

## Common Commands

```bash
# Start development services
./deploy.sh dev

# Stop all services
./deploy.sh stop

# Show service status
./deploy.sh status

# Follow all logs
./deploy.sh logs

# Follow one service log
./deploy.sh logs backend

# Run database migrations inside the backend container
./deploy.sh migrate

# Validate Docker Compose configuration without printing secrets
./deploy.sh config
```

## Development Notes

- Use Docker Compose as the default runtime path for normal development.
- The root `.env` file is the source of runtime configuration.
- `backend/.env` is managed as a symlink to `../.env` by `deploy.sh`.
- Backend business logic belongs in the service layer and should use dependency
  injection provider functions.
- Frontend API clients live in `frontend/src/apis/`.
- Use `ApiResponse` for backend API responses.
- Use `TIMESTAMP(timezone=True)` for database time fields and use `String` plus
  application validation instead of database enum types.

## API Documentation

When `ENV` is `development` or `preview`, the backend exposes documentation
navigation and API docs:

- Client Swagger UI: `/client/docs`
- Client ReDoc: `/client/redoc`
- Backoffice Swagger UI: `/backoffice/docs`
- Backoffice ReDoc: `/backoffice/redoc`
- OpenAPI exports: `/api-docs/client.json` and `/api-docs/backoffice.json`

In production, root documentation navigation is hidden, while direct
documentation URLs remain controlled by the application configuration.

## Testing

Backend tests can be run inside the backend environment:

```bash
docker compose exec backend pytest
```

Frontend checks can be run from the frontend workspace when local dependencies
are installed:

```bash
cd frontend
pnpm lint
pnpm type-check
pnpm build
```

## Security

- Never commit `.env`, `.env.local`, `.env.production`, or real credential files.
- Use `.env.example` as the configuration template.
- Keep provider secrets, AWS credentials, JWT secrets, and mail credentials in
  local environment files or deployment secrets.
- Rotate credentials immediately if they are accidentally shared.

## More Documentation

- Backend guide: `backend/README.md`
- Backend architecture docs: `backend/docs/architecture/`
- Backend API docs: `backend/docs/api/`
- Backend deployment notes: `backend/docs/`
