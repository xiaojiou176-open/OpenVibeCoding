#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _request_json(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected payload from {url}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize recent CI route report artifacts from GitHub Actions.")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--per-route-limit", type=int, default=5)
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-markdown", required=True)
    return parser.parse_args()


def collect_route_rows(items: list[dict[str, Any]], *, per_route_limit: int) -> tuple[dict[str, list[dict[str, Any]]], float]:
    routes = {"untrusted_pr": [], "trusted_pr": [], "push_main": [], "workflow_dispatch": []}
    prefixes = {route: f"ci-route-report-{route}-" for route in routes}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        for route, prefix in prefixes.items():
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            status, _, suffix = rest.partition("-")
            routes[route].append(
                {
                    "name": name,
                    "status": status,
                    "created_at": item.get("created_at"),
                    "expired": bool(item.get("expired")),
                    "workflow_run": item.get("workflow_run") or {},
                    "suffix": suffix,
                }
            )
            break
    for route in routes:
        routes[route].sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        del routes[route][per_route_limit:]
    coverage = sum(1 for route, rows in routes.items() if rows) / len(routes)
    return routes, coverage


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"❌ [ci-route-recent] missing token env: {args.token_env}")
        return 1
    owner, repo = args.repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts?per_page=100"
    try:
        payload = _request_json(url, token)
    except urllib.error.HTTPError as exc:
        print(f"❌ [ci-route-recent] github api error: {exc.code}")
        return 1
    except Exception as exc:
        print(f"❌ [ci-route-recent] request failed: {exc}")
        return 1

    items = payload.get("artifacts")
    if not isinstance(items, list):
        print("❌ [ci-route-recent] invalid artifact payload")
        return 1

    routes, coverage = collect_route_rows(items, per_route_limit=args.per_route_limit)
    payload_out = {
        "report_type": "openvibecoding_ci_recent_route_reports",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": args.repo,
        "per_route_limit": args.per_route_limit,
        "route_coverage_score": coverage,
        "routes": routes,
    }
    out_json = Path(args.out_json).expanduser().resolve()
    out_md = Path(args.out_markdown).expanduser().resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## Recent CI Route Reports",
        "",
        f"- repo: `{args.repo}`",
        f"- route_coverage_score: `{coverage:.2f}`",
        "",
    ]
    for route, rows in routes.items():
        lines.append(f"### {route}")
        if rows:
            lines.extend(
                [
                    f"- status=`{row['status']}` created_at=`{row['created_at']}` expired=`{row['expired']}` name=`{row['name']}`"
                    for row in rows
                ]
            )
        else:
            lines.append("- none")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(str(out_json))
    print(str(out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
