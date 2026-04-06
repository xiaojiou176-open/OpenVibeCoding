# Langfuse (Addon)

This folder ships a starter `docker-compose.yml` and `.env.example`.
Keep Langfuse out of the core execution path until `events.jsonl` is stable.

Runbook:
1. `cp .env.example .env`
2. Set `DATABASE_URL` in `.env` using your own local Postgres DSN that matches your local user, password, host, port, and database name.
3. Update all remaining `REPLACE_WITH_*` values in `.env` (required; compose is fail-closed for secret-like keys).
4. Generate strong secrets where needed (for example: `openssl rand -hex 32` for `ENCRYPTION_KEY`).
5. `docker compose up -d`
6. Open Langfuse Web at `http://localhost:18130` (host port; container internal web port remains `3000`).
7. Local exposed infra ports are pinned to CortexPilot `18xxx` namespace:
   - Postgres: `127.0.0.1:18132 -> 5432`
   - Redis: `127.0.0.1:18179 -> 6379`
   - MinIO API: `127.0.0.1:18190 -> 9000`

OTel bridge:
- The `otel-collector` service listens on `127.0.0.1:4317` (gRPC) / `127.0.0.1:4318` (HTTP).
- Configure Langfuse OTLP endpoint + auth via env:
  - `LANGFUSE_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel` (internal docker network)
  - `LANGFUSE_OTLP_AUTH=<base64(public_key:secret_key)>`
- S3-related external endpoints default to MinIO host mapping:
  - `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT=http://localhost:18190`
  - `LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT=http://localhost:18190`
- Then set orchestrator env:
  - `CORTEXPILOT_OTLP_ENDPOINT=http://127.0.0.1:4318`
  - `CORTEXPILOT_OTLP_PROTOCOL=http`
  - `CORTEXPILOT_OTLP_HEADERS=Authorization=Basic <base64>`
Note: Langfuse OTel ingestion expects HTTP/protobuf, not gRPC.
