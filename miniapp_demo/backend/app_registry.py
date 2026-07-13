"""小程序注册表：扫描 / 解析 app.yaml -> AppManifest，以及新建小程序脚手架。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import config


@dataclass
class ScriptDef:
    name: str
    path: str
    visibility: List[str] = field(default_factory=lambda: ["agent", "ui"])


@dataclass
class SkillDef:
    content_file_path: str = "SKILL.md"
    binding_tools: List[str] = field(default_factory=lambda: ["bash", "app_emit"])


@dataclass
class InjectRoundDef:
    user: str
    assistant: str


@dataclass
class OnInitConfig:
    user_message: str = ""


@dataclass
class OnExitConfig:
    inject_round: Optional[InjectRoundDef] = None


def _ui_rel(entry: str) -> str:
    """把 app 根相对的 entry 路径转成 assets/ui/ 下的相对文件名(用于 UI 静态服务)。"""
    if not entry:
        return "index.html"
    marker = "assets/ui/"
    return entry.split(marker, 1)[-1] if marker in entry else entry


@dataclass
class AppManifest:
    id: str
    name: str
    version: str
    entry_ui: str
    description: str
    scripts: List[ScriptDef]
    skill: SkillDef
    root: Path
    entry_desktop: Optional[str] = None
    entry_mobile: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    on_init: Optional[OnInitConfig] = None
    on_exit: Optional[OnExitConfig] = None

    def script_by_name(self, name: str) -> Optional[ScriptDef]:
        for s in self.scripts:
            if s.name == name:
                return s
        return None

    def entries(self) -> Dict[str, Optional[str]]:
        """各设备入口的 UI 相对文件名(供前端按设备加载)。desktop/mobile 缺省为 None。"""
        return {
            "default": _ui_rel(self.entry_ui),
            "desktop": _ui_rel(self.entry_desktop) if self.entry_desktop else None,
            "mobile": _ui_rel(self.entry_mobile) if self.entry_mobile else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "entry_ui": self.entry_ui,
            "entries": self.entries(),
            "description": self.description,
            "scripts": [
                {"name": s.name, "path": s.path, "visibility": s.visibility}
                for s in self.scripts
            ],
            "skill": {
                "content_file_path": self.skill.content_file_path,
                "binding_tools": self.skill.binding_tools,
            },
            "permissions": self.permissions,
        }


def app_dir(app_id: str) -> Path:
    return config.APPS_DIR / app_id


def _parse_manifest(root: Path) -> Optional[AppManifest]:
    yaml_path = root / "app.yaml"
    if not yaml_path.exists():
        return None
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    scripts = [
        ScriptDef(
            name=s["name"],
            path=s["path"],
            visibility=s.get("visibility", ["agent", "ui"]),
        )
        for s in (data.get("scripts") or [])
    ]
    skill_raw = data.get("skill") or {}
    skill = SkillDef(
        content_file_path=skill_raw.get("content_file_path", "SKILL.md"),
        binding_tools=skill_raw.get("binding_tools", ["bash", "app_emit"]),
    )
    entry_cfg = data.get("entry") or {}
    entry = entry_cfg.get("ui", "assets/ui/index.html")
    on_init: Optional[OnInitConfig] = None
    init_raw = data.get("on_init")
    if isinstance(init_raw, dict) and init_raw.get("user_message"):
        on_init = OnInitConfig(user_message=init_raw["user_message"])

    on_exit: Optional[OnExitConfig] = None
    exit_raw = data.get("on_exit")
    if isinstance(exit_raw, dict):
        ir = exit_raw.get("inject_round")
        if isinstance(ir, dict) and "user" in ir and "assistant" in ir:
            on_exit = OnExitConfig(
                inject_round=InjectRoundDef(user=ir["user"], assistant=ir["assistant"]),
            )

    return AppManifest(
        id=data.get("id", root.name),
        name=data.get("name", root.name),
        version=str(data.get("version", "1.0")),
        entry_ui=entry,
        description=data.get("description", ""),
        scripts=scripts,
        skill=skill,
        root=root,
        entry_desktop=entry_cfg.get("desktop"),
        entry_mobile=entry_cfg.get("mobile"),
        permissions=list(data.get("permissions") or []),
        on_init=on_init,
        on_exit=on_exit,
    )


def list_apps() -> List[AppManifest]:
    config.ensure_directories()
    out: List[AppManifest] = []
    for child in sorted(config.APPS_DIR.iterdir()):
        if not child.is_dir():
            continue
        manifest = _parse_manifest(child)
        if manifest:
            out.append(manifest)
    return out


def get_app(app_id: str) -> Optional[AppManifest]:
    root = app_dir(app_id)
    if not root.is_dir():
        return None
    return _parse_manifest(root)


_ID_RE = re.compile(r"[^a-z0-9-]+")


def slugify(name: str) -> str:
    slug = _ID_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "app"


def create_app(name: str, description: str = "") -> AppManifest:
    """新建一个最小可用的小程序脚手架。"""
    config.ensure_directories()
    app_id = slugify(name)
    root = app_dir(app_id)
    suffix = 1
    while root.exists():
        suffix += 1
        app_id = f"{slugify(name)}-{suffix}"
        root = app_dir(app_id)

    (root / "scripts").mkdir(parents=True)
    (root / "assets" / "ui").mkdir(parents=True)
    (root / "assets" / "schema").mkdir(parents=True)

    app_yaml = {
        "id": app_id,
        "name": name,
        "version": "1.0",
        "description": description,
        "entry": {"ui": "assets/ui/index.html"},
        "scripts": [
            {"name": "hello", "path": "scripts/hello.py", "visibility": ["agent", "ui"]},
        ],
        "skill": {"content_file_path": "SKILL.md", "binding_tools": ["bash", "app_emit"]},
    }
    with open(root / "app.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(app_yaml, f, allow_unicode=True, sort_keys=False)

    (root / "SKILL.md").write_text(
        f"# {name}\n\n{description or '一个新的小程序。'}\n\n"
        "## 能力\n\n"
        "- 通过 `bash` 运行 `scripts/` 下的脚本处理业务数据。\n"
        "- 应用脚本通过 `miniapp_runtime` 的 `emit_ui` 更新小程序界面；"
        "stdout 只输出供 Agent 阅读的普通摘要。\n"
        "- Agent 需要直接更新界面时使用 `app_emit`。\n",
        encoding="utf-8",
    )

    (root / "scripts" / "hello.py").write_text(
        '#!/usr/bin/env python3\n'
        '"""direct_action 示例脚本：通过 MiniApp Runtime 更新界面。"""\n'
        "from miniapp_runtime import emit_ui\n\n"
        "emit_ui({\"message\": \"hello from "
        + app_id
        + "\"})\n"
        "print(\"hello action completed\")\n",
        encoding="utf-8",
    )

    (root / "assets" / "ui" / "index.html").write_text(
        _STARTER_UI.replace("{{APP_NAME}}", name),
        encoding="utf-8",
    )
    return _parse_manifest(root)  # type: ignore[return-value]


_STARTER_UI = """<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{APP_NAME}}</title>
  <script src="/sdk/miniapp.js"></script>
  <style>
    :root { --accent-grad: linear-gradient(135deg,#6366f1,#8b5cf6); --line:#eceff4; --muted:#64748b; }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", system-ui, sans-serif;
      margin: 0; padding: 28px 30px; color: #0b1120;
      background: radial-gradient(700px 380px at 100% -5%, rgba(124,58,237,.07), transparent 60%), #f7f8fb;
      -webkit-font-smoothing: antialiased;
    }
    .head { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; }
    .logo { width: 42px; height: 42px; border-radius: 12px; background: var(--accent-grad); display: flex;
      align-items: center; justify-content: center; color: #fff; font-size: 20px;
      box-shadow: 0 8px 20px rgba(124,58,237,.4), inset 0 1px 0 rgba(255,255,255,.25); }
    h1 { font-size: 20px; margin: 0; letter-spacing: -.02em; }
    .subtitle { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .card { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 18px;
      box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 10px 28px rgba(16,24,40,.06); margin-bottom: 18px; }
    .row { display: flex; gap: 10px; align-items: center; }
    input { flex: 1; padding: 11px 14px; border: 1px solid #dbe1ea; border-radius: 11px; outline: none; }
    input:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.25); }
    button { padding: 11px 18px; border-radius: 11px; border: none; cursor: pointer; font-weight: 650; color: #fff;
      background: var(--accent-grad); box-shadow: 0 6px 16px rgba(99,102,241,.32); transition: filter .15s ease; }
    button:hover { filter: brightness(1.06); }
    .label { font-size: 12px; font-weight: 700; color: #334155; margin-bottom: 8px; }
    pre { background: #f8fafc; border: 1px solid var(--line); padding: 12px; border-radius: 12px; overflow: auto; margin: 0; }
    .traj { color: #a5b4fc; font-size: 12px; white-space: pre-wrap; background: #0b1020; border-radius: 12px;
      padding: 12px 14px; min-height: 24px; font-family: ui-monospace, Menlo, monospace; }
  </style>
</head>
<body>
  <div class="head">
    <div class="logo">◆</div>
    <div>
      <h1>{{APP_NAME}}</h1>
      <div class="subtitle">direct_action 直连脚本 · agent_action 交给 AI</div>
    </div>
  </div>
  <div class="card">
    <div class="row">
      <button id="hello">运行 hello (direct_action)</button>
    </div>
  </div>
  <div class="card">
    <div class="row">
      <input id="intent" placeholder="问问 AI…" />
      <button id="ask">AI (agent_action)</button>
    </div>
  </div>
  <div class="card">
    <div class="label">界面数据 (ui_update)</div>
    <pre id="data">{}</pre>
  </div>
  <div class="card">
    <div class="label">AI 轨迹 (trajectory)</div>
    <div class="traj" id="traj"></div>
  </div>

  <script>
    const dataEl = document.getElementById('data');
    const trajEl = document.getElementById('traj');
    miniapp.onUiUpdate((e) => { dataEl.textContent = JSON.stringify(e.payload.structuredContent, null, 2); });
    miniapp.onTrajectory((e) => {
      if (e.type === 'thinking') trajEl.textContent += '[think] ' + (e.payload.delta || '') + '\\n';
      else if (e.type === 'text') trajEl.textContent += (e.payload.delta || '');
      else if (e.type === 'tool_call') trajEl.textContent += '\\n[tool] ' + e.payload.name + ' ' + JSON.stringify(e.payload.arguments) + '\\n';
      else if (e.type === 'tool_result') trajEl.textContent += '[result] ' + (e.payload.resultSummary || '') + '\\n';
    });
    document.getElementById('hello').onclick = () => {
      trajEl.textContent = '';
      miniapp.directAction('hello', {}, { onData: (e) => { dataEl.textContent = JSON.stringify(e.payload.structuredContent, null, 2); } });
    };
    document.getElementById('ask').onclick = () => {
      trajEl.textContent = '';
      const intent = document.getElementById('intent').value;
      miniapp.agentAction(intent, {});
    };
  </script>
</body>
</html>
"""
