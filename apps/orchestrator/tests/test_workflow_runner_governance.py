from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "check_workflow_runner_governance.py"
    spec = importlib.util.spec_from_file_location("check_workflow_runner_governance", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_workflow(root: Path, name: str, body: str) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / name).write_text(body, encoding="utf-8")


def test_workflow_runner_governance_accepts_hosted_runner_temp_contract() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_ok"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    env:
      AGENT_TOOLSDIRECTORY: ${{ runner.temp }}/hostedtoolcache-job
      RUNNER_TOOL_CACHE: ${{ runner.temp }}/hostedtoolcache-job
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          clean: true
      - run: echo ok
""".strip(),
    )
    assert module.check_root(tmp_root) == []


def test_workflow_runner_governance_rejects_workspace_cache_paths() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_workspace"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    env:
      AGENT_TOOLSDIRECTORY: ${{ github.workspace }}/.runtime-cache/hostedtoolcache
    steps:
      - run: echo ok
""".strip(),
    )
    violations = module.check_root(tmp_root)
    assert any("AGENT_TOOLSDIRECTORY" in item for item in violations)


def test_workflow_runner_governance_rejects_non_standard_runs_on_and_runner_registration() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_bad_runs_on"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - run: ./config.sh
""".strip(),
    )
    violations = module.check_root(tmp_root)
    assert any("runs-on must be exactly one of" in item for item in violations)
    assert any("runner registration command" in item for item in violations)


def test_workflow_runner_governance_rejects_checkout_without_explicit_clean_true() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_missing_clean"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          fetch-depth: 0
      - run: echo ok
""".strip(),
    )
    violations = module.check_root(tmp_root)
    assert any("clean: true" in item for item in violations)


def test_workflow_runner_governance_accepts_checkout_with_explicit_clean_true() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_explicit_clean"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          persist-credentials: false
          fetch-depth: 0
          clean: true
      - run: echo ok
""".strip(),
    )
    violations = module.check_root(tmp_root)
    assert not any("clean: true" in item for item in violations)


def test_workflow_runner_governance_accepts_container_entry_lane() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_container_entry"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  full-ci:
    runs-on: ubuntu-24.04
    env:
      AGENT_TOOLSDIRECTORY: ${{ runner.temp }}/hostedtoolcache-job
      RUNNER_TOOL_CACHE: ${{ runner.temp }}/hostedtoolcache-job
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          persist-credentials: false
          clean: true
      - run: bash scripts/docker_ci.sh ci
""".strip(),
    )
    assert module.check_root(tmp_root) == []


def test_workflow_runner_governance_accepts_github_hosted_low_privilege_lane() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_gh_hosted"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  trust-gate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          clean: true
      - run: bash scripts/docker_ci.sh lane basic-gates
""".strip(),
    )
    assert module.check_root(tmp_root) == []


def test_workflow_runner_governance_rejects_unpinned_action_reference() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_unpinned_action"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          clean: true
      - run: echo ok
""".strip(),
    )
    violations = module.check_root(tmp_root)
    assert any("pin a full commit SHA" in item for item in violations)


def test_workflow_runner_governance_accepts_action_subpath_pinned_to_commit_sha() -> None:
    module = _load_module()
    tmp_root = Path.cwd() / ".runtime-cache" / "test_output" / "workflow_runner_governance_subpath_sha"
    if tmp_root.exists():
        import shutil

        shutil.rmtree(tmp_root)
    _write_workflow(
        tmp_root,
        "ci.yml",
        """
name: test
jobs:
  demo:
    runs-on: ubuntu-24.04
    steps:
      - uses: github/codeql-action/init@ebcb5b36ded6beda4ceefea6a8bc4cc885255bb3
        with:
          languages: python
      - run: echo ok
""".strip(),
    )
    assert module.check_root(tmp_root) == []
