#!/usr/bin/env python3
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_ROOT = ROOT / "apps" / "desktop" / "src-tauri" / "icons"
IOS_ROOT = ICON_ROOT / "ios"


PNG_TARGETS = {
    ICON_ROOT / "icon-1024.png": 1024,
    ICON_ROOT / "icon.png": 512,
    ICON_ROOT / "128x128.png": 128,
    ICON_ROOT / "128x128@2x.png": 256,
    ICON_ROOT / "64x64.png": 64,
    ICON_ROOT / "32x32.png": 32,
    ICON_ROOT / "Square30x30Logo.png": 30,
    ICON_ROOT / "Square44x44Logo.png": 44,
    ICON_ROOT / "Square71x71Logo.png": 71,
    ICON_ROOT / "Square89x89Logo.png": 89,
    ICON_ROOT / "Square107x107Logo.png": 107,
    ICON_ROOT / "Square142x142Logo.png": 142,
    ICON_ROOT / "Square150x150Logo.png": 150,
    ICON_ROOT / "Square284x284Logo.png": 284,
    ICON_ROOT / "Square310x310Logo.png": 310,
    ICON_ROOT / "StoreLogo.png": 50,
    IOS_ROOT / "AppIcon-20x20@1x.png": 20,
    IOS_ROOT / "AppIcon-20x20@2x.png": 40,
    IOS_ROOT / "AppIcon-20x20@2x-1.png": 40,
    IOS_ROOT / "AppIcon-20x20@3x.png": 60,
    IOS_ROOT / "AppIcon-29x29@1x.png": 29,
    IOS_ROOT / "AppIcon-29x29@2x.png": 58,
    IOS_ROOT / "AppIcon-29x29@2x-1.png": 58,
    IOS_ROOT / "AppIcon-29x29@3x.png": 87,
    IOS_ROOT / "AppIcon-40x40@1x.png": 40,
    IOS_ROOT / "AppIcon-40x40@2x.png": 80,
    IOS_ROOT / "AppIcon-40x40@2x-1.png": 80,
    IOS_ROOT / "AppIcon-40x40@3x.png": 120,
    IOS_ROOT / "AppIcon-60x60@2x.png": 120,
    IOS_ROOT / "AppIcon-60x60@3x.png": 180,
    IOS_ROOT / "AppIcon-76x76@1x.png": 76,
    IOS_ROOT / "AppIcon-76x76@2x.png": 152,
    IOS_ROOT / "AppIcon-83.5x83.5@2x.png": 167,
    IOS_ROOT / "AppIcon-512@2x.png": 1024,
}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICONSET_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def _write_png(path: Path, size: int) -> bytes:
    pixels = bytearray()
    radius = 0.23

    for y in range(size):
        pixels.append(0)
        ny = (y + 0.5) / size
        for x in range(size):
            nx = (x + 0.5) / size
            rgba = _pixel(nx, ny, radius)
            pixels.extend(rgba)

    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(bytes(pixels), level=9)),
            _png_chunk(b"IEND", b""),
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _pixel(nx: float, ny: float, radius: float) -> tuple[int, int, int, int]:
    # Rounded-square silhouette.
    if _outside_rounded_square(nx, ny, radius):
        return (0, 0, 0, 0)

    top = (8, 18, 34)
    bottom = (20, 53, 94)
    accent = (63, 215, 197)
    glow = (138, 237, 226)
    white = (246, 250, 255)

    # Background vertical gradient.
    t = max(0.0, min(1.0, ny))
    bg = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))

    # Soft accent sweep.
    sweep = max(0.0, 1.0 - (((nx - 0.24) ** 2) / 0.060 + ((ny - 0.18) ** 2) / 0.020))
    bg = tuple(min(255, round(bg[i] + accent[i] * sweep * 0.22)) for i in range(3))

    # Stylized "J" mark: top bar + shaft + hook + terminal dot.
    j_mask = 0.0
    if 0.31 <= nx <= 0.70 and 0.25 <= ny <= 0.34:
        j_mask = 1.0
    if 0.55 <= nx <= 0.66 and 0.25 <= ny <= 0.68:
        j_mask = 1.0
    hook = ((nx - 0.48) ** 2) / 0.024 + ((ny - 0.67) ** 2) / 0.030
    if hook <= 1.0 and nx <= 0.62 and ny >= 0.53:
        j_mask = 1.0
    dot = ((nx - 0.28) ** 2) / 0.0018 + ((ny - 0.28) ** 2) / 0.0018
    dot_mask = 1.0 if dot <= 1.0 else 0.0
    accent_bar = 1.0 if 0.19 <= nx <= 0.28 and 0.17 <= ny <= 0.83 else 0.0

    rgb = list(bg)
    if accent_bar:
        rgb = [round(accent[i] * 0.85 + bg[i] * 0.15) for i in range(3)]
    if j_mask:
        rgb = [round(white[i] * 0.92 + bg[i] * 0.08) for i in range(3)]
    if dot_mask:
        rgb = [round(glow[i] * 0.9 + bg[i] * 0.1) for i in range(3)]

    return (*rgb, 255)


def _outside_rounded_square(nx: float, ny: float, radius: float) -> bool:
    cx = min(max(nx, radius), 1 - radius)
    cy = min(max(ny, radius), 1 - radius)
    dx = nx - cx
    dy = ny - cy
    return dx * dx + dy * dy > radius * radius


def _write_ico(path: Path) -> None:
    images: list[tuple[int, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="openvibecoding-icon-ico-") as tmp:
        tmp_dir = Path(tmp)
        for size in ICO_SIZES:
            payload = _write_png(tmp_dir / f"{size}.png", size)
            images.append((size, payload))

        count = len(images)
        header = struct.pack("<HHH", 0, 1, count)
        directory = bytearray()
        offset = 6 + count * 16
        blobs = bytearray()
        for size, payload in images:
            directory.extend(
                struct.pack(
                    "<BBBBHHII",
                    0 if size >= 256 else size,
                    0 if size >= 256 else size,
                    0,
                    0,
                    1,
                    32,
                    len(payload),
                    offset,
                )
            )
            blobs.extend(payload)
            offset += len(payload)
        path.write_bytes(header + bytes(directory) + bytes(blobs))


def _write_icns(path: Path) -> None:
    if shutil.which("iconutil") is None:
        raise SystemExit("iconutil is required to generate icon.icns on this host")

    with tempfile.TemporaryDirectory(prefix="openvibecoding-iconset-", suffix=".iconset") as tmp:
        iconset = Path(tmp)
        mapping = {
            16: "icon_16x16.png",
            32: "icon_16x16@2x.png",
            32.1: "icon_32x32.png",
            64: "icon_32x32@2x.png",
            128: "icon_128x128.png",
            256: "icon_128x128@2x.png",
            256.1: "icon_256x256.png",
            512: "icon_256x256@2x.png",
            512.1: "icon_512x512.png",
            1024: "icon_512x512@2x.png",
        }

        # Use fractional keys to preserve distinct filenames at identical source sizes.
        for marker, filename in mapping.items():
            size = int(marker)
            _write_png(iconset / filename, size)

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(path)],
            check=True,
            cwd=ROOT,
        )


def main() -> int:
    ICON_ROOT.mkdir(parents=True, exist_ok=True)
    IOS_ROOT.mkdir(parents=True, exist_ok=True)

    for path, size in PNG_TARGETS.items():
        _write_png(path, size)

    _write_ico(ICON_ROOT / "icon.ico")
    _write_icns(ICON_ROOT / "icon.icns")
    print(f"generated first-party desktop icon bundle under {ICON_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
