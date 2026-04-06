#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def _socket_path_from_host(host: str) -> Path | None:
    if not host or not host.startswith("unix://"):
        return None
    parsed = urlparse(host)
    if not parsed.path:
        return None
    return Path(parsed.path)


def _current_context_socket() -> Path | None:
    try:
        proc = subprocess.run(
            ["docker", "context", "inspect"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not payload:
        return None
    host = str(payload[0].get("Endpoints", {}).get("docker", {}).get("Host", "")).strip()
    return _socket_path_from_host(host)


def _candidate_sockets() -> list[Path]:
    candidates: list[Path] = []
    env_host = _socket_path_from_host(os.environ.get("DOCKER_HOST", "").strip())
    if env_host is not None:
        candidates.append(env_host)
    context_host = _current_context_socket()
    if context_host is not None:
        candidates.append(context_host)
    candidates.extend(
        [
            Path("/var/run/docker.sock"),
            Path.home() / ".docker" / "run" / "docker.sock",
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _probe_socket(sock_path: Path, timeout_sec: float) -> tuple[bool, str]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout_sec)
    try:
        client.connect(str(sock_path))
        client.sendall(b"GET /_ping HTTP/1.0\r\nHost: docker\r\n\r\n")
        data = client.recv(512)
    finally:
        client.close()
    text = data.decode("utf-8", "replace")
    if "200 OK" in text:
        return True, f"docker socket {sock_path} responded 200 OK"
    body = text.split("\r\n\r\n", 1)[1].strip() if "\r\n\r\n" in text else text.strip()
    status_line = text.splitlines()[0].strip() if text.splitlines() else "unknown"
    return False, f"docker socket {sock_path} responded with {status_line}: {body or 'empty response'}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Docker daemon health via unix sockets.")
    parser.add_argument("--timeout-sec", type=float, default=3.0)
    args = parser.parse_args()

    unavailable_messages: list[str] = []
    missing_candidates: list[str] = []

    for sock_path in _candidate_sockets():
        if not sock_path.exists():
            missing_candidates.append(str(sock_path))
            continue
        if not sock_path.is_socket():
            unavailable_messages.append(f"docker socket path is not a socket: {sock_path}")
            continue
        try:
            healthy, message = _probe_socket(sock_path, args.timeout_sec)
        except socket.timeout:
            unavailable_messages.append(f"docker socket {sock_path} timed out during /_ping probe")
            continue
        except OSError as exc:
            unavailable_messages.append(f"docker socket {sock_path} probe failed: {exc}")
            continue
        if healthy:
            sys.stdout.write(f"unix://{sock_path}\n")
            return 0
        unavailable_messages.append(message)

    if unavailable_messages:
        sys.stderr.write(unavailable_messages[0] + "\n")
        return 125
    if missing_candidates:
        sys.stderr.write(
            "docker daemon probe found no usable socket candidates: " + ", ".join(missing_candidates) + "\n"
        )
        return 125
    sys.stderr.write("docker daemon probe found no usable socket candidates\n")
    return 125


if __name__ == "__main__":
    raise SystemExit(main())
