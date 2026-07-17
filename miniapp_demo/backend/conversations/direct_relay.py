"""Generic direct action relay — no skill-specific business logic."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import sandbox, stores
from ..app_registry import AppManifest, get_app
from .agent_lane import ActionRecord


@dataclass
class DirectRelayResult:
    ok: bool
    ui_commands: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    summary: str = ""


class DirectRelay:
    def __init__(self, user: str = "local"):
        self.user = user

    async def execute(self, action: ActionRecord) -> DirectRelayResult:
        if not action.skill_id or not action.name:
            return DirectRelayResult(ok=False, error="skillId and name are required")

        manifest = get_app(action.skill_id)
        if manifest is None:
            return DirectRelayResult(ok=False, error="skill not found")

        script = manifest.script_by_name(action.name)
        if script is None or "ui" not in script.visibility:
            return DirectRelayResult(ok=False, error=f"unknown action: {action.name}")

        store_dir = stores.business_store_dir(
            stores.session_id_for(self.user, action.skill_id)
        )
        result = await sandbox.run_script(
            manifest.root / script.path,
            manifest.root,
            store_dir,
            action.args,
        )
        ui_commands = _ui_commands_from_metadata(result.miniapp_metadata)
        if result.ok:
            count = len(ui_commands)
            summary = (
                f"completed with {count} UI command"
                f"{'' if count == 1 else 's'}"
            )
            return DirectRelayResult(ok=True, ui_commands=ui_commands, summary=summary)

        error = result.error or f"exit code {result.exit_code}"
        return DirectRelayResult(ok=False, error=error, summary=f"failed: {error}")


def _ui_commands_from_metadata(metadata: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not metadata:
        return []
    commands: List[Dict[str, Any]] = []
    for item in metadata.get("uiUpdates") or []:
        if isinstance(item, dict) and item.get("type") == "ui_command":
            commands.append(item)
        else:
            commands.append({"type": "ui_command", "command": "patch", "payload": item})
    for item in metadata.get("uiCommands") or []:
        if isinstance(item, dict):
            commands.append(item)
    return commands
