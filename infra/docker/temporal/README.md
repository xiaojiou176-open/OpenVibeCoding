# Temporal (Addon)

This folder ships a starter `docker-compose.yml` and `.env.example`.
Do not replace OpenVibeCoding events until the governance model is stable.

Runbook:
1. `cp .env.example .env`
2. Set `TEMPORAL_POSTGRES_PASSWORD` in `.env` and replace any `REPLACE_WITH_*` values.
3. Adjust version variables in `.env` as needed.
4. `docker compose up -d`
