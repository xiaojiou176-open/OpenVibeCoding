# Docker Addons

This directory holds docker-compose templates for addon systems.
These services are installed early but integrated later.

Available templates:
- `infra/docker/langfuse/docker-compose.yml`
- `infra/docker/temporal/docker-compose.yml`

Security note:
- Both addons are fail-closed for secret-like env vars.
- Copy each `.env.example` to `.env` and replace every `REPLACE_WITH_*` value before `docker compose up -d`.
