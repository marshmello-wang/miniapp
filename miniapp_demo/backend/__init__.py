"""miniapp_demo backend package.

On import, ensure the forge_os repo root (which contains the `common` package,
i.e. agent_framework + llm) is importable. Override with FORGE_OS_ROOT env var.
"""
import os
import sys
from pathlib import Path


def _bootstrap_forge_os_path() -> None:
    candidates = []
    env = os.environ.get("FORGE_OS_ROOT")
    if env:
        candidates.append(Path(env))

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "forge_os")
        if parent.name == "code":
            break

    for candidate in candidates:
        if (candidate / "common").is_dir():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return

    raise RuntimeError(
        "Could not locate forge_os root (containing `common/`). "
        "Set FORGE_OS_ROOT env var to the forge_os directory."
    )


_bootstrap_forge_os_path()
