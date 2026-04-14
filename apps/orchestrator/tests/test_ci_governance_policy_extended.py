from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _base_policy() -> dict:
    return {
        "workflow_file": ".github/workflows/ci.yml",
        "concurrency": {"group": "ci-${{ github.workflow }}-${{ github.ref }}", "cancel_in_progress": True},
        "required_jobs": [
            "ci-trust-boundary",
            "quick-feedback",
            "untrusted-pr-basic-gates",
            "policy-and-security",
            "core-tests",
            "ui-truth",
            "resilience-and-e2e",
            "release-evidence",
            "pr-release-critical-gates",
            "pr-ci-gate",
        ],
        "runner_contract": {
            "github_hosted": [
                "ci-trust-boundary",
                "quick-feedback",
                "untrusted-pr-basic-gates",
                "policy-and-security",
                "core-tests",
                "ui-truth",
                "resilience-and-e2e",
                "release-evidence",
                "pr-release-critical-gates",
                "pr-ci-gate",
            ],
        },
        "trusted_semantic_jobs": [
            "policy-and-security",
            "core-tests",
        ],
        "artifact_roots_required": [".runtime-cache/test_output", ".runtime-cache/logs", ".runtime-cache/openvibecoding/reports"],
        "artifact_roots_release_required": [".runtime-cache/openvibecoding/release"],
        "retry_green_policy": {"max_retry_green_count": 0},
        "slice_slo_sec": {
            "quick-feedback": 300,
            "policy-and-security": 3600,
            "core-tests": 5400,
            "ui-truth": 7200,
            "resilience-and-e2e": 7200,
            "release-evidence": 5400,
        },
        "runner_quarantine": {
            "retry_green_count_blocking": 1,
            "slo_breach_count_blocking": 1,
            "doctor_failure_blocking": True,
            "drift_failure_blocking": True,
        },
        "route_contract": {
            "untrusted_pr": {
                "event_names": ["pull_request"],
                "trust_class": "untrusted",
                "runner_class": "github_hosted",
                "cloud_bootstrap_allowed": False,
                "required_jobs": ["ci-trust-boundary", "quick-feedback", "untrusted-pr-basic-gates", "pr-ci-gate"],
                "required_artifact_prefixes": ["ci-pr-low-priv-artifacts-", "ci-route-report-untrusted_pr-"],
            },
            "trusted_pr": {
                "event_names": ["pull_request"],
                "trust_class": "trusted",
                "runner_class": "github_hosted",
                "cloud_bootstrap_allowed": False,
                "required_jobs": [
                    "ci-trust-boundary",
                    "quick-feedback",
                    "policy-and-security",
                    "core-tests",
                    "pr-release-critical-gates",
                    "pr-ci-gate",
                ],
                "required_artifact_prefixes": [
                    "ci-policy-and-security-artifacts-",
                    "ci-core-tests-artifacts-",
                    "ci-route-report-trusted_pr-",
                ],
            },
            "push_main": {
                "event_names": ["push"],
                "trust_class": "trusted",
                "runner_class": "github_hosted",
                "cloud_bootstrap_allowed": False,
                "required_jobs": ["ci-trust-boundary", "quick-feedback", "policy-and-security", "core-tests"],
                "required_artifact_prefixes": ["ci-quick-feedback-artifacts-", "ci-policy-and-security-artifacts-", "ci-core-tests-artifacts-"],
            },
            "workflow_dispatch": {
                "event_names": ["workflow_dispatch"],
                "trust_class": "trusted",
                "runner_class": "github_hosted",
                "cloud_bootstrap_allowed": True,
                "required_jobs": ["ci-trust-boundary", "quick-feedback", "policy-and-security", "core-tests"],
                "required_artifact_prefixes": ["ci-quick-feedback-artifacts-", "ci-policy-and-security-artifacts-", "ci-core-tests-artifacts-"],
            },
        },
        "protected_dispatch_contract": {
            "required_environment": "owner-approved-sensitive",
            "manual_only_jobs": {
                "ui-truth": "run_ui_truth",
                "resilience-and-e2e": "run_resilience_and_e2e",
                "release-evidence": "run_release_evidence",
            },
        },
        "strict_env_contract": {
            "allowlisted_openvibecoding_env": [
                "OPENVIBECODING_DOC_GATE_MODE",
                "OPENVIBECODING_DOC_GATE_BASE_SHA",
                "OPENVIBECODING_DOC_GATE_HEAD_SHA",
                "OPENVIBECODING_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE",
                "OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE",
                "OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE",
                "OPENVIBECODING_CI_ROUTE_ID",
                "OPENVIBECODING_CI_TRUST_CLASS",
                "OPENVIBECODING_CI_RUNNER_CLASS",
                "OPENVIBECODING_CI_CLOUD_BOOTSTRAP_ALLOWED",
            ],
            "forbid_dotenv_fallback": True,
        },
        "freshness_contract": {
            "max_report_age_sec": 172800,
            "required_report_metadata_fields": ["generated_at", "source_run_id", "source_route", "source_event"],
            "analytics_only_blacklist_paths": [".runtime-cache/test_output/changed_scope_quality/meta/truth_status.json"],
        },
        "supply_chain": {"allowed_action_repos": [], "allowed_download_hosts": []},
    }


def _workflow_text(*, include_route_artifact: bool = True, include_allowlist: bool = True) -> tuple[str, str]:
    workflow = """
name: CI
on:
  workflow_dispatch:
    inputs:
      run_ui_truth:
        required: false
      run_resilience_and_e2e:
        required: false
      run_release_evidence:
        required: false
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  ci-trust-boundary:
    runs-on: ubuntu-24.04
    outputs:
      trusted_route_allowed: ${{ steps.decide.outputs.trusted_route_allowed }}
      sensitive_dispatch_allowed: ${{ steps.decide.outputs.sensitive_dispatch_allowed }}
      route_id: ${{ steps.decide.outputs.route_id }}
      trust_class: ${{ steps.decide.outputs.trust_class }}
      runner_class: ${{ steps.decide.outputs.runner_class }}
    steps:
      - id: decide
        run: |
          echo "trusted_route_allowed=true" >> "$GITHUB_OUTPUT"
          echo "sensitive_dispatch_allowed=true" >> "$GITHUB_OUTPUT"
          echo "route_id=workflow_dispatch" >> "$GITHUB_OUTPUT"
          echo "trust_class=trusted" >> "$GITHUB_OUTPUT"
          echo "runner_class=github_hosted" >> "$GITHUB_OUTPUT"
  quick-feedback:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: ci-quick-feedback-artifacts-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
  untrusted-pr-basic-gates:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: ci-pr-low-priv-artifacts-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
  policy-and-security:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
            .runtime-cache/openvibecoding/release
  core-tests:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
  ui-truth:
    if: needs.ci-trust-boundary.outputs.trusted_route_allowed == 'true' && needs.ci-trust-boundary.outputs.sensitive_dispatch_allowed == 'true' && github.event_name == 'workflow_dispatch' && github.event.inputs.run_ui_truth == 'true'
    environment: owner-approved-sensitive
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
  resilience-and-e2e:
    if: needs.ci-trust-boundary.outputs.trusted_route_allowed == 'true' && needs.ci-trust-boundary.outputs.sensitive_dispatch_allowed == 'true' && github.event_name == 'workflow_dispatch' && github.event.inputs.run_resilience_and_e2e == 'true'
    environment: owner-approved-sensitive
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/reports
  release-evidence:
    if: needs.ci-trust-boundary.outputs.trusted_route_allowed == 'true' && needs.ci-trust-boundary.outputs.sensitive_dispatch_allowed == 'true' && github.event_name == 'workflow_dispatch' && github.event.inputs.run_release_evidence == 'true'
    environment: owner-approved-sensitive
    runs-on: ubuntu-24.04
    needs: [policy-and-security, core-tests, ui-truth, resilience-and-e2e]
    steps:
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: |
            .runtime-cache/test_output
            .runtime-cache/logs
            .runtime-cache/openvibecoding/release
            .runtime-cache/openvibecoding/reports
          name: ci-route-report-${{ needs.ci-trust-boundary.outputs.route_id }}-${{ github.run_id }}
  pr-release-critical-gates:
    runs-on: ubuntu-24.04
    needs: [ci-trust-boundary, quick-feedback, policy-and-security, core-tests]
    steps:
      - run: |
          python3 scripts/build_ci_route_report.py finalize \
            --job-observed ci-trust-boundary \
            --job-observed quick-feedback \
            --job-observed policy-and-security \
            --job-observed core-tests \
            --job-observed pr-release-critical-gates \
            --artifact-name ci-policy-and-security-artifacts-${{ github.run_id }}-${{ github.run_attempt }} \
            --artifact-name ci-core-tests-artifacts-${{ github.run_id }}-${{ github.run_attempt }}
  pr-ci-gate:
    runs-on: ubuntu-24.04
    needs: [quick-feedback, ci-trust-boundary, pr-release-critical-gates]
"""
    docker_ci = """
STRICT_CI_OPENVIBECODING_ENV_ALLOWLIST=(
  OPENVIBECODING_DOC_GATE_MODE
  OPENVIBECODING_DOC_GATE_BASE_SHA
  OPENVIBECODING_DOC_GATE_HEAD_SHA
  OPENVIBECODING_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE
  OPENVIBECODING_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE
  OPENVIBECODING_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE
  OPENVIBECODING_CI_ROUTE_ID
  OPENVIBECODING_CI_TRUST_CLASS
  OPENVIBECODING_CI_RUNNER_CLASS
  OPENVIBECODING_CI_CLOUD_BOOTSTRAP_ALLOWED
)
append_strict_ci_openvibecoding_allowlist
if [[ ! -v "${var_name}" ]] && ! is_truthy "${GITHUB_ACTIONS:-0}"; then
  :
fi
"""
    if not include_allowlist:
        docker_ci = "STRICT_CI_OPENVIBECODING_ENV_ALLOWLIST=(\n  OPENVIBECODING_DOC_GATE_MODE\n)\n"
    if not include_route_artifact:
        workflow = workflow.replace(
            "          name: ci-route-report-${{ needs.ci-trust-boundary.outputs.route_id }}-${{ github.run_id }}\n",
            "",
        )
    return workflow, docker_ci


def test_policy_checker_accepts_dynamic_route_artifact_prefixes(tmp_path: Path) -> None:
    root = tmp_path / "repo-ok"
    workflow_text, docker_ci_text = _workflow_text()
    _write(root, ".github/workflows/ci.yml", workflow_text)
    _write(root, "scripts/docker_ci.sh", docker_ci_text)
    policy_path = root / "configs" / "ci_governance_policy.json"
    _write(root, "configs/ci_governance_policy.json", json.dumps(_base_policy()))

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_ci_governance_policy.py"),
            "--root",
            str(root),
            "--policy",
            str(policy_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_policy_checker_rejects_trusted_pr_route_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo-trusted-route-drift"
    workflow_text, docker_ci_text = _workflow_text()
    _write(root, ".github/workflows/ci.yml", workflow_text)
    _write(root, "scripts/docker_ci.sh", docker_ci_text)
    policy = _base_policy()
    policy["route_contract"]["trusted_pr"]["required_jobs"].insert(5, "resilience-and-e2e")
    policy["route_contract"]["trusted_pr"]["required_artifact_prefixes"].insert(2, "ci-resilience-and-e2e-artifacts-")
    policy_path = root / "configs" / "ci_governance_policy.json"
    _write(root, "configs/ci_governance_policy.json", json.dumps(policy))

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_ci_governance_policy.py"),
            "--root",
            str(root),
            "--policy",
            str(policy_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "details=redacted_for_safe_logging" in (proc.stdout + proc.stderr)


def test_policy_checker_rejects_strict_allowlist_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo-bad"
    workflow_text, docker_ci_text = _workflow_text(include_allowlist=False)
    _write(root, ".github/workflows/ci.yml", workflow_text)
    _write(root, "scripts/docker_ci.sh", docker_ci_text)
    policy_path = root / "configs" / "ci_governance_policy.json"
    _write(root, "configs/ci_governance_policy.json", json.dumps(_base_policy()))

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_ci_governance_policy.py"),
            "--root",
            str(root),
            "--policy",
            str(policy_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "violations" in (proc.stdout + proc.stderr)
    assert "count=" in (proc.stdout + proc.stderr)


def test_policy_checker_accepts_parameter_expansion_strict_dotenv_boundary(tmp_path: Path) -> None:
    root = tmp_path / "repo-parameter-expansion"
    workflow_text, docker_ci_text = _workflow_text()
    docker_ci_text = docker_ci_text.replace(
        'if [[ ! -v "${var_name}" ]] && ! is_truthy "${GITHUB_ACTIONS:-0}"; then',
        'if [[ -z "${!var_name+x}" ]] && ! is_truthy "${GITHUB_ACTIONS:-0}"; then',
    )
    _write(root, ".github/workflows/ci.yml", workflow_text)
    _write(root, "scripts/docker_ci.sh", docker_ci_text)
    policy_path = root / "configs" / "ci_governance_policy.json"
    _write(root, "configs/ci_governance_policy.json", json.dumps(_base_policy()))

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_ci_governance_policy.py"),
            "--root",
            str(root),
            "--policy",
            str(policy_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_ci_download_artifacts_restore_runtime_layout_instead_of_workspace_root() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert workflow_text.count("path: .runtime-cache\n") == 4
    assert workflow_text.count("path: .runtime-cache/openvibecoding/reports/ci/routes\n") == 4
    assert 'echo "ROUTE_ID=${ROUTE_ID}"' in workflow_text
    assert '} >> "${GITHUB_ENV}"' in workflow_text
    assert "uses: actions/download-artifact" in workflow_text
    assert "path: .\n" not in workflow_text
