#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMO_DIR="$ROOT_DIR/tooling/remotion-promo"
POSTER_OUT="$ROOT_DIR/docs/assets/storefront/openvibecoding-command-tower-teaser-poster.png"
VIDEO_OUT="$ROOT_DIR/docs/assets/storefront/openvibecoding-command-tower-teaser.mp4"

if [[ ! -d "$PROMO_DIR" ]]; then
  echo "❌ [storefront-teaser] missing promo source: $PROMO_DIR" >&2
  exit 1
fi

cleanup() {
  rm -rf "$PROMO_DIR/node_modules"
}
trap cleanup EXIT INT TERM

echo "🚀 [storefront-teaser] install standalone promo dependencies"
pnpm --dir "$PROMO_DIR" install --ignore-workspace

echo "🚀 [storefront-teaser] typecheck"
(cd "$PROMO_DIR" && ./node_modules/.bin/tsc --noEmit)

echo "🚀 [storefront-teaser] render poster"
(
  cd "$PROMO_DIR"
  ./node_modules/.bin/remotion still src/index.ts OpenVibeCodingTeaser "$POSTER_OUT" --frame=480
)

echo "🚀 [storefront-teaser] render video"
(
  cd "$PROMO_DIR"
  ./node_modules/.bin/remotion render src/index.ts OpenVibeCodingTeaser "$VIDEO_OUT" --codec=h264 --crf=23
)

echo "✅ [storefront-teaser] rendered:"
echo "   poster: $POSTER_OUT"
echo "   video : $VIDEO_OUT"
