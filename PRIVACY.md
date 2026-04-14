# Privacy Notes

OpenVibeCoding is source code, not a hosted service.

## Default Local Behavior

Unless you explicitly configure external integrations, expected runtime output
stays local:

- logs under `.runtime-cache/logs/`
- test and governance artifacts under `.runtime-cache/test_output/`
- runtime-generated contracts under `.runtime-cache/openvibecoding/contracts/`

## Sensitive Data Rules

- do not commit real credentials or local `.env` files
- do not commit runtime traces, screenshots, or evidence bundles containing
  private data
- redact tokens, cookies, and personal data before sharing logs or screenshots

## Optional Integrations

Some workflows can be connected to external telemetry or tracing providers. If
you enable them in your own environment, you are responsible for reviewing the
provider terms and your own data-handling obligations.
