"""Read and validate metadata emitted by a MiniApp script process."""
from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

MAX_LINE_BYTES = 64 * 1024
MAX_FILE_BYTES = 1024 * 1024


class MetadataError(ValueError):
    """Base class for invalid script result metadata."""


class MetadataValidationError(MetadataError):
    """Raised when an NDJSON event does not match the metadata protocol."""


class MetadataSizeError(MetadataError):
    """Raised when metadata exceeds a configured byte limit."""


def _reject_non_finite_constant(constant: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {constant}")


def _validate_json_values(value: Any, active: set[int] | None = None) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MetadataValidationError(
                "metadata contains a non-finite number"
            )
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise MetadataValidationError(
                "metadata strings must be valid UTF-8"
            ) from exc
        return
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
                    raise MetadataValidationError(
                        "metadata object keys must be strings"
                    )
                _validate_json_values(key, active)
                _validate_json_values(nested_value, active)
        else:
            for nested_value in value:
                _validate_json_values(nested_value, active)
    finally:
        active.remove(identity)


def create_result_file(directory: Path | None = None) -> Path:
    """Create a unique, empty result file accessible only by its owner."""
    fd, raw_path = tempfile.mkstemp(
        prefix="miniapp-result-", suffix=".ndjson", dir=directory
    )
    path = Path(raw_path)
    try:
        os.fchmod(fd, 0o600)
    except BaseException:
        try:
            os.close(fd)
        finally:
            path.unlink(missing_ok=True)
        raise
    else:
        os.close(fd)
    return path


def cleanup_result_file(path: Path) -> None:
    """Remove a result file, including after a failed script invocation."""
    Path(path).unlink(missing_ok=True)


@contextmanager
def result_file(directory: Path | None = None) -> Iterator[Path]:
    """Yield a result file and always remove it when the scope exits."""
    path = create_result_file(directory)
    try:
        yield path
    finally:
        cleanup_result_file(path)


def validate_event(event: Any) -> dict[str, Any]:
    """Validate one decoded metadata event and return it."""
    if not isinstance(event, dict):
        raise MetadataValidationError("metadata event must be a JSON object")
    _validate_json_values(event)

    event_type = event.get("type")
    if event_type == "ui_update":
        if set(event) != {"type", "structuredContent"}:
            raise MetadataValidationError("invalid ui_update event fields")
        if not isinstance(event["structuredContent"], dict):
            raise MetadataValidationError(
                "ui_update structuredContent must be a JSON object"
            )
    elif event_type == "agent_signal":
        if set(event) != {"type", "agentSignal"}:
            raise MetadataValidationError("invalid agent_signal event fields")
        if event["agentSignal"] != "end_turn":
            raise MetadataValidationError(
                "agent_signal only supports agentSignal=end_turn"
            )
    else:
        raise MetadataValidationError(f"unsupported metadata event type: {event_type!r}")

    return event


def read_ndjson(
    path: Path,
    *,
    max_line_bytes: int = MAX_LINE_BYTES,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> list[dict[str, Any]]:
    """Read, decode, and validate result events after the process exits."""
    path = Path(path)
    if path.stat().st_size > max_file_bytes:
        raise MetadataSizeError(
            f"metadata file exceeds {max_file_bytes} byte limit"
        )

    events: list[dict[str, Any]] = []
    with path.open("rb") as result:
        for line_number, raw_line in enumerate(result, start=1):
            if len(raw_line) > max_line_bytes:
                raise MetadataSizeError(
                    f"metadata line {line_number} exceeds "
                    f"{max_line_bytes} byte limit"
                )
            try:
                event = json.loads(
                    raw_line, parse_constant=_reject_non_finite_constant
                )
            except (UnicodeDecodeError, ValueError) as exc:
                raise MetadataValidationError(
                    f"invalid JSON on metadata line {line_number}"
                ) from exc
            events.append(validate_event(event))
    return events


def aggregate_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate validated events into the script tool-result metadata shape."""
    ui_updates: list[dict[str, Any]] = []
    agent_signal = None
    for raw_event in events:
        event = validate_event(dict(raw_event))
        if event["type"] == "ui_update":
            ui_updates.append(event["structuredContent"])
        else:
            agent_signal = "end_turn"
    return {"uiUpdates": ui_updates, "agentSignal": agent_signal}


def parse_result_file(
    path: Path,
    *,
    max_line_bytes: int = MAX_LINE_BYTES,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Explicitly parse result metadata when the caller accepts script output."""
    return aggregate_events(
        read_ndjson(
            path,
            max_line_bytes=max_line_bytes,
            max_file_bytes=max_file_bytes,
        )
    )
