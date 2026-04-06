from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol

from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.runners.codex_runner import CodexRunner
from cortexpilot_orch.store.run_store import RunStore

ContractDict = dict[str, Any]
TaskResult = dict[str, Any]


class ExecutionAdapter(Protocol):
    name: str

    def supports(self, *, runner_name: str | None = None, provider: str | None = None) -> bool:
        ...

    def execute(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        ...

    def resume(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        resume_id: str | None = None,
        mock_mode: bool = False,
    ) -> TaskResult:
        ...

    def run_contract(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        ...


class BaseExecutionAdapter(ABC):
    name: str

    @abstractmethod
    def supports(self, *, runner_name: str | None = None, provider: str | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run_contract(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        raise NotImplementedError

    def execute(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        return self.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    def resume(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        resume_id: str | None = None,
        mock_mode: bool = False,
    ) -> TaskResult:
        resume_contract = self._with_resume_id(contract, resume_id)
        return self.run_contract(resume_contract, worktree_path, schema_path, mock_mode=mock_mode)

    def _with_resume_id(self, contract: ContractDict, resume_id: str | None) -> ContractDict:
        if not isinstance(resume_id, str) or not resume_id.strip():
            return contract
        cloned = copy.deepcopy(contract)
        assigned = cloned.get("assigned_agent")
        if not isinstance(assigned, dict):
            assigned = {}
            cloned["assigned_agent"] = assigned
        assigned["codex_thread_id"] = resume_id.strip()
        return cloned


class CodexExecutionAdapter(BaseExecutionAdapter):
    name = "codex"

    def __init__(self, run_store: RunStore) -> None:
        self._runner = CodexRunner(run_store)

    def supports(self, *, runner_name: str | None = None, provider: str | None = None) -> bool:
        runner = str(runner_name or "").strip().lower()
        provider_name = str(provider or "").strip().lower()
        return runner == "codex" or provider_name == "codex"

    def run_contract(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        return self._runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)


class ClaudeExecutionAdapter(BaseExecutionAdapter):
    name = "claude"
    _FORCED_PROVIDER = "anthropic"

    def __init__(self, run_store: RunStore) -> None:
        self._runner = AgentsRunner(run_store)

    def supports(self, *, runner_name: str | None = None, provider: str | None = None) -> bool:
        runner = str(runner_name or "").strip().lower()
        provider_name = str(provider or "").strip().lower()
        return runner == "claude" or provider_name in {"claude", "anthropic"}

    def run_contract(
        self,
        contract: ContractDict,
        worktree_path: Path,
        schema_path: Path,
        *,
        mock_mode: bool = False,
    ) -> TaskResult:
        adapted_contract = self._with_mcp_first_hint(contract)
        return self._runner.run_contract(adapted_contract, worktree_path, schema_path, mock_mode=mock_mode)

    def _with_mcp_first_hint(self, contract: ContractDict) -> ContractDict:
        cloned = copy.deepcopy(contract)
        runtime_options = cloned.get("runtime_options")
        if not isinstance(runtime_options, dict):
            runtime_options = {}
            cloned["runtime_options"] = runtime_options
        execution = runtime_options.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            runtime_options["execution"] = execution
        execution.setdefault("mcp_first", True)
        runtime_options["provider"] = self._FORCED_PROVIDER
        return cloned


def build_execution_adapter(
    *,
    run_store: RunStore,
    runner_name: str | None = None,
    provider: str | None = None,
) -> BaseExecutionAdapter:
    normalized_runner = str(runner_name or "").strip().lower()
    normalized_provider = str(provider or "").strip().lower()

    if normalized_runner == "codex" or normalized_provider == "codex":
        return CodexExecutionAdapter(run_store)

    if normalized_runner == "claude" or normalized_provider in {"claude", "anthropic"}:
        return ClaudeExecutionAdapter(run_store)

    raise ValueError(
        "execution adapter unsupported runner/provider: "
        f"runner={normalized_runner or '<empty>'}, provider={normalized_provider or '<empty>'}"
    )
