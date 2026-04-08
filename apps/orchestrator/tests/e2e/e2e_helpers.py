from __future__ import annotations

import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable


# --------------------
# Git helpers
# --------------------

def _git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def init_repo(repo: Path) -> None:
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def _write_allowlist(repo: Path) -> None:
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    allowlist = {
        "version": "v1",
        "allow": [
            {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
            {"exec": "git", "argv_prefixes": [["git"]]},
            {"exec": "echo", "argv_prefixes": [["echo"]]},
            {"exec": "python", "argv_prefixes": [["python"], ["python", "-m"]]},
            {"exec": "python3", "argv_prefixes": [["python3"], ["python3", "-m"]]},
        ],
        "deny_substrings": ["rm -rf", "sudo", "ssh ", "scp ", "sftp ", "curl ", "wget "],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")


def create_tiny_repo(base_dir: Path) -> Path:
    repo = base_dir
    repo.mkdir(parents=True, exist_ok=True)
    init_repo(repo)
    _write_allowlist(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)
    return repo


def _acquire_ui_lock(repo_root: Path):
    lock_dir = repo_root / ".runtime-cache" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (lock_dir / "dashboard_e2e_ui.lock").open("a+", encoding="utf-8")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    return lock_file


# --------------------
# Process helpers
# --------------------


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _orchestrator_cli_cmd(repo_root: Path, *args: str) -> list[str]:
    uv_bin = shutil.which("uv") or "uv"
    requirements_path = repo_root / "apps" / "orchestrator" / "requirements.txt"
    return [
        uv_bin,
        "run",
        "--no-project",
        "--with-requirements",
        str(requirements_path),
        "python",
        "-m",
        "cortexpilot_orch.cli",
        *args,
    ]


def wait_for_http(url: str, timeout_s: int, proc: "ManagedProcess") -> None:
    deadline = time.monotonic() + timeout_s
    last_error: str | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"process exited early for {url}:\n{proc.read_log()}"
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {url}: {last_error}\n{proc.read_log()}")


def load_json(url: str) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = resp.read().decode("utf-8")
        return json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"failed to load json from {url}: {exc}") from exc


def parse_run_id(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("run_id="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"run_id not found in output: {stdout}")


class ManagedProcess:
    def __init__(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str],
        log_path: Path,
        on_stop: Callable[[], None] | None = None,
    ) -> None:
        self._log_path = log_path
        self._on_stop = on_stop
        self._log_file = log_path.open("w", encoding="utf-8")
        self._proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=self._log_file,
            stderr=self._log_file,
            text=True,
        )

    def poll(self) -> int | None:
        return self._proc.poll()

    def read_log(self) -> str:
        if self._log_path.exists():
            return self._log_path.read_text(encoding="utf-8")
        return ""

    def stop(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._log_file.close()
        if self._on_stop is not None:
            self._on_stop()


# --------------------
# E2E orchestration helpers
# --------------------


def build_env(repo_root: Path, runtime_root: Path, runs_root: Path, worktree_root: Path) -> dict[str, str]:
    base_env = os.environ.copy()
    pythonpath_entries = [
        str(repo_root / "apps" / "orchestrator" / "src"),
        str(repo_root),
    ]
    if base_env.get("PYTHONPATH"):
        pythonpath_entries.append(base_env["PYTHONPATH"])
    base_env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    base_env["CORTEXPILOT_RUNTIME_ROOT"] = str(runtime_root)
    base_env["CORTEXPILOT_RUNS_ROOT"] = str(runs_root)
    base_env["CORTEXPILOT_WORKTREE_ROOT"] = str(worktree_root)
    base_env["CORTEXPILOT_SCHEMA_ROOT"] = str(repo_root / "schemas")
    base_env["CORTEXPILOT_CONTRACT_ROOT"] = str(runtime_root / "contracts")
    base_env["CORTEXPILOT_TOOL_REGISTRY"] = str(repo_root / "tooling" / "registry.json")
    base_env["CORTEXPILOT_AGENT_REGISTRY"] = str(repo_root / "policies" / "agent_registry.json")
    base_env["NEXT_TELEMETRY_DISABLED"] = "1"
    return base_env


def start_api(repo_root: Path, env: dict[str, str], log_path: Path) -> tuple[ManagedProcess, int]:
    api_port = free_port()
    api_cmd = _orchestrator_cli_cmd(repo_root, "serve", "--host", "127.0.0.1", "--port", str(api_port))
    return ManagedProcess(api_cmd, cwd=repo_root, env=env, log_path=log_path), api_port


def start_ui(repo_root: Path, env: dict[str, str], api_port: int, log_path: Path) -> tuple[ManagedProcess, int]:
    ui_port = free_port()
    ui_env = dict(env)
    ui_env["NEXT_PUBLIC_CORTEXPILOT_API_BASE"] = f"http://127.0.0.1:{api_port}"
    # Isolate Next.js dev lock/artifacts per E2E process to avoid cross-stage lock contention.
    next_dist_dir = f".next-e2e-{ui_port}"
    ui_env["NEXT_DIST_DIR"] = next_dist_dir
    ui_cmd = ["npm", "run", "dev", "--", "--port", str(ui_port)]

    lock_file = _acquire_ui_lock(repo_root)
    dashboard_dir = repo_root / "apps" / "dashboard"

    def _cleanup_on_stop() -> None:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()
        # Clean up isolated Next.js build artifacts to prevent disk bloat.
        e2e_dist_path = dashboard_dir / next_dist_dir
        if e2e_dist_path.exists() and e2e_dist_path.is_dir():
            shutil.rmtree(e2e_dist_path, ignore_errors=True)

    try:
        proc = ManagedProcess(
            ui_cmd,
            cwd=dashboard_dir,
            env=ui_env,
            log_path=log_path,
            on_stop=_cleanup_on_stop,
        )
    except Exception:  # noqa: BLE001
        _cleanup_on_stop()
        raise

    return (proc, ui_port)


def run_contract(repo: Path, env: dict[str, str], contract: dict[str, Any], tmp_path: Path) -> str:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    run_cmd = _orchestrator_cli_cmd(repo_root, "run", str(contract_path), "--mock")
    result = subprocess.run(run_cmd, cwd=repo, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return parse_run_id(result.stdout)


def run_chain(repo: Path, env: dict[str, str], chain: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    run_cmd = _orchestrator_cli_cmd(repo_root, "run-chain", str(chain_path), "--mock")
    result = subprocess.run(run_cmd, cwd=repo, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    output = result.stdout.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid chain report json: {output}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected chain report payload: {payload}")
    return payload


def run_replay(repo: Path, env: dict[str, str], run_id: str) -> str:
    run_cmd = [
        sys.executable,
        "-m",
        "cortexpilot_orch.cli",
        "replay",
        run_id,
    ]
    result = subprocess.run(run_cmd, cwd=repo, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout
