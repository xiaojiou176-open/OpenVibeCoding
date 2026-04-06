#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def resolve_github_token() -> str | None:
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    if shutil.which("gh") is None:
        return None

    token_proc = subprocess.run(
        ["gh", "auth", "token"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    token = token_proc.stdout.strip()
    if token_proc.returncode == 0 and token:
        return token
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed when the live GitHub repository still has open secret-scanning "
            "or code-scanning alerts."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "require", "off"),
        default="auto",
        help="require = fail on query/auth errors, auto = advisory-skip on query/auth errors, off = skip entirely",
    )
    parser.add_argument(
        "--repo",
        help="owner/repo override; defaults to the repository inferred from origin",
    )
    return parser.parse_args()


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(cmd)}")
    return proc.stdout


def infer_repo_slug() -> str:
    raw = run(["git", "remote", "get-url", "origin"]).strip()
    if raw.startswith("git@github.com:"):
        slug = raw[len("git@github.com:") :]
        return slug[:-len(".git")] if slug.endswith(".git") else slug
    parsed = urlparse(raw)
    if parsed.netloc == "github.com" and parsed.path:
        slug = parsed.path.lstrip("/")
        return slug[:-len(".git")] if slug.endswith(".git") else slug
    raise RuntimeError(f"unable to infer GitHub repository from origin remote: {raw}")


def gh_api_json(path: str) -> list[dict[str, object]]:
    token = resolve_github_token()
    if not token:
        raise RuntimeError("missing GitHub token: set GH_TOKEN/GITHUB_TOKEN or authenticate gh")

    request = Request(
        f"https://api.github.com/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cortexpilot-github-alert-gate",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = body or exc.reason or f"HTTP {exc.code}"
        raise RuntimeError(f"GitHub API request failed for {path}: HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API request failed for {path}: {exc.reason}") from exc
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError(f"expected list payload from GitHub API {path}, got {type(data).__name__}")
    return data


def main() -> int:
    args = parse_args()
    if args.mode == "off":
        print("ℹ️ [github-security-alerts] gate skipped (mode=off)")
        return 0

    repo = args.repo or infer_repo_slug()
    try:
        secret_alerts = gh_api_json(f"repos/{repo}/secret-scanning/alerts?state=open&per_page=100")
        code_alerts = gh_api_json(f"repos/{repo}/code-scanning/alerts?state=open&per_page=100")
    except RuntimeError as exc:
        if args.mode == "auto":
            print(f"ℹ️ [github-security-alerts] advisory skip (mode=auto): {exc}")
            return 0
        print(f"❌ [github-security-alerts] required query failed: {exc}")
        return 1

    violations: list[str] = []
    if secret_alerts:
        violations.append(f"open secret-scanning alerts: {len(secret_alerts)}")
    if code_alerts:
        violations.append(f"open code-scanning alerts: {len(code_alerts)}")

    if violations:
        print("❌ [github-security-alerts] live GitHub security alerts remain open:")
        for item in violations:
            print(f"- {item}")
        print(f"- repo: {repo}")
        return 1

    print(
        "✅ [github-security-alerts] live GitHub secret-scanning/code-scanning alerts are clear "
        f"for {repo}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
