from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from types import ModuleType


_DISCOVERED_SUBMODULES = tuple(
    sorted(
        module_info.name
        for module_info in iter_modules(__path__)
        if not module_info.name.startswith("_")
    )
)

__all__ = list(_DISCOVERED_SUBMODULES)


def __getattr__(name: str) -> ModuleType:
    if name not in _DISCOVERED_SUBMODULES:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    module = import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted({*globals(), *_DISCOVERED_SUBMODULES})
