# OpenVibeCoding Remotion Promo

Repo-owned source for a short OpenVibeCoding promo video.

This folder is intentionally standalone so we can iterate on public-facing video
assets without expanding the main workspace graph.

## Commands

```bash
pnpm --dir tooling/remotion-promo install
pnpm --dir tooling/remotion-promo studio
pnpm --dir tooling/remotion-promo render:poster
pnpm --dir tooling/remotion-promo render:mp4
```

## Outputs

- Poster: `docs/assets/storefront/openvibecoding-command-tower-teaser-poster.png`
- MP4: `.runtime-cache/openvibecoding/media/openvibecoding-command-tower-teaser.mp4`

The tracked public asset is the poster image. The MP4 first renders into
runtime cache so we can inspect size and quality before deciding whether it
belongs on the public surface.
