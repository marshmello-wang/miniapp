"""Helpers for scripts to emit trusted result metadata outside stdout."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_RESULT_PATH_ENV = "MINIAPP_RESULT_PATH"


class MiniAppRuntimeError(RuntimeError):
    """Raised when the script SDK cannot emit valid metadata."""


def _validate_object_keys(value: Any, active: set[int] | None = None) -> None:
    if not isinstance(value, (dict, list, tuple)):
        return

    active = active if active is not None else set()
    identity = id(value)
    if identity in active:
        return
    active.add(identity)
    try:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if not isinstance(key, str):
                    raise MiniAppRuntimeError(
                        "metadata object keys must be strings"
                    )
                _validate_object_keys(nested_value, active)
        else:
            for nested_value in value:
                _validate_object_keys(nested_value, active)
    finally:
        active.remove(identity)


def _result_path() -> Path:
    raw_path = os.environ.get(_RESULT_PATH_ENV)
    if not raw_path:
        raise MiniAppRuntimeError(f"{_RESULT_PATH_ENV} is required")
    return Path(raw_path)


def _append_event(event: dict[str, Any]) -> None:
    _validate_object_keys(event)
    try:
        payload = (
            json.dumps(
                event,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MiniAppRuntimeError(
            "metadata event must be valid UTF-8 strict JSON"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise MiniAppRuntimeError(
            "metadata event must contain only strict JSON values"
        ) from exc
    try:
        with _result_path().open("ab") as result:
            result.write(payload)
    except OSError as exc:
        raise MiniAppRuntimeError("failed to write metadata result file") from exc


def emit_ui(structured_content: dict[str, Any]) -> None:
    """Append one structured UI update to this invocation's result file."""
    if not isinstance(structured_content, dict):
        raise TypeError("structuredContent must be a dict")
    _append_event(
        {"type": "ui_update", "structuredContent": structured_content}
    )


def end_turn() -> None:
    """Ask the calling agent runtime to end its current turn."""
    _append_event({"type": "agent_signal", "agentSignal": "end_turn"})
