#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE_DIR="$ROOT_DIR/docs/assets/storefront"
EXPORT_DIR="$STORE_DIR/.export"

SOCIAL_SOURCE="$STORE_DIR/social-preview-source.svg"
SOCIAL_PNG="$STORE_DIR/social-preview-1280x640.png"
STORYBOARD_SOURCE="$STORE_DIR/first-loop-storyboard.svg"
STORYBOARD_PNG="$STORE_DIR/first-loop-storyboard.png"
STORYBOARD_GIF="$STORE_DIR/first-loop-storyboard.gif"

mkdir -p "$EXPORT_DIR"

cleanup_exports() {
  rm -rf "$EXPORT_DIR"
}
trap cleanup_exports EXIT INT TERM

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "❌ missing required command: $name" >&2
    exit 1
  fi
}

require_any_command() {
  local found=0
  local name
  for name in "$@"; do
    if command -v "$name" >/dev/null 2>&1; then
      found=1
      break
    fi
  done
  if [[ "$found" -eq 0 ]]; then
    echo "❌ missing required command group: need one of $*" >&2
    exit 1
  fi
}

render_svg_png() {
  local source="$1"
  local output="$2"
  local size="$3"
  local base
  local tmp_png
  base="$(basename "$source")"
  tmp_png="$EXPORT_DIR/$base.png"

  if command -v sips >/dev/null 2>&1; then
    sips -s format png "$source" --out "$tmp_png" >/dev/null 2>&1
    sips --resampleWidth "$size" "$tmp_png" --out "$tmp_png" >/dev/null 2>&1
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "$source" --export-type=png --export-filename="$tmp_png" --export-width="$size" >/dev/null 2>&1
  elif command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "$size" -a -o "$tmp_png" "$source" >/dev/null 2>&1
  else
    echo "❌ no available SVG->PNG renderer found (need one of: sips, inkscape, rsvg-convert)" >&2
    exit 1
  fi

  if [[ ! -f "$tmp_png" ]]; then
    echo "❌ failed to export preview for $source" >&2
    exit 1
  fi
  cp "$tmp_png" "$output"
}

require_command ffmpeg
require_any_command sips inkscape rsvg-convert

render_svg_png "$SOCIAL_SOURCE" "$SOCIAL_PNG" 1280
render_svg_png "$STORYBOARD_SOURCE" "$STORYBOARD_PNG" 1440

ffmpeg -y \
  -loop 1 -t 2 -i "$STORYBOARD_PNG" \
  -lavfi "fps=8,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=single[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  "$STORYBOARD_GIF" >/dev/null 2>&1

echo "✅ storefront assets exported"
echo "   social preview: $SOCIAL_PNG"
echo "   storyboard png: $STORYBOARD_PNG"
echo "   storyboard gif: $STORYBOARD_GIF"
