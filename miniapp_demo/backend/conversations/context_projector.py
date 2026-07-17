"""Skill-owned business context projection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .. import sandbox, stores
from ..app_registry import get_app

CONTEXT_SNAPSHOT_SCRIPT = "context_snapshot"


async def project_business_context(
    *,
    skill_id: str,
    view_snapshot: Dict[str, Any],
    user: str = "local",
) -> Dict[str, Any]:
    manifest = get_app(skill_id)
    if manifest is None:
        raise ValueError(f"skill not found: {skill_id}")

    base = {
        "skillId": skill_id,
        "uiInstanceId": view_snapshot.get("uiInstanceId"),
        "route": view_snapshot.get("route"),
        "revision": view_snapshot.get("revision"),
        "view": dict(view_snapshot.get("env") or {}),
        "business": {},
    }

    script = manifest.script_by_name(CONTEXT_SNAPSHOT_SCRIPT)
    if script is None:
        return base

    store_dir = stores.business_store_dir(stores.session_id_for(user, skill_id))
    result = await sandbox.run_script(
        manifest.root / script.path,
        manifest.root,
        store_dir,
        {"viewSnapshot": view_snapshot},
    )
    if not result.ok:
        raise RuntimeError(result.error or f"context_snapshot failed: exit {result.exit_code}")

    business = _extract_business_payload(result.stdout, result.miniapp_metadata)
    if business is not None:
        base["business"] = business
    return base


def _extract_business_payload(
    stdout: str,
    metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if metadata:
        payload = metadata.get("businessContext")
        if isinstance(payload, dict):
            return payload
        for update in metadata.get("uiUpdates") or []:
            if isinstance(update, dict) and isinstance(update.get("business"), dict):
                return update["business"]

    text = (stdout or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("business"), dict):
        return parsed["business"]
    if isinstance(parsed, dict):
        return parsed
    return None
