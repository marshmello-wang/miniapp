"""配置与运行时目录管理。

~/.miniapp/
├── config.json          # LLM / agent 配置
├── messages.db          # agent 消息存储 (MessageStore, sqlite)
├── apps/                # 已安装的小程序 (skill 包)
│   └── {appId}/ ...
└── sessions/            # 每个小程序 session 的业务 store
    └── {sessionId}/store.json
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


MINIAPP_HOME = Path.home() / ".miniapp"
CONFIG_FILE = MINIAPP_HOME / "config.json"
APPS_DIR = MINIAPP_HOME / "apps"
SESSIONS_DIR = MINIAPP_HOME / "sessions"
MESSAGES_DB = MINIAPP_HOME / "messages.db"

# 随仓库自带的种子小程序目录
BUNDLED_APPS_DIR = Path(__file__).resolve().parent.parent / "apps"
# 随仓库自带的 widget SDK
SDK_DIR = Path(__file__).resolve().parent.parent / "sdk"

DEFAULT_USER = "local"

# 与 lite_code 完全一致的 llm / agent / memory 配置结构
DEFAULT_CONFIG: Dict[str, Any] = {
    "llm": {
        "provider": "claude",
        "api_key": "",
        "model": "claude-sonnet-4-20250514",
        "base_url": None,
    },
    "agent": {
        "max_iterations": 30,
        "max_tokens": 8192,
        "temperature": 0.7,
        "thinking_level": "medium",
    },
    # 录音文件识别极速版(AUC submit/query)。凭证来自控制台"创建应用并开通
    # 录音文件识别极速版服务":appid / token / cluster(应用页的 Cluster ID)。
    "asr": {
        "appid": "",
        "token": "",
        "cluster": "",
        "timeout": 60,
    },
    "memory": {
        "l1": {
            "budget": {
                "max_total_tokens": 128000,
                "system_prompt_tokens": 4000,
                "memory_tokens": 4000,
                "react_stack_reserve": 10000,
                "final_output_reserve": 16000,
            },
            "history_collapse": {
                "thinking_collapse": {"type": "remove"},
                "tool_call_collapse": {"type": "none"},
                "tool_response_collapse": {
                    "type": "prefix",
                    "collapse_prefix_length": 200,
                },
            },
            "tool_response_collapse_whitelist": ["text_edit"],
        },
        "l2": {
            "history_collapse": {
                "thinking_collapse": {"type": "remove"},
                "tool_call_collapse": {"type": "remove"},
                "tool_response_collapse": {
                    "type": "prefix",
                    "collapse_prefix_length": 100,
                },
            },
            "after_collapse_max_length": 94000,
            "protected_steps": 1,
            "fallback_strategy": "abandon",
        },
    },
}


def ensure_directories() -> None:
    MINIAPP_HOME.mkdir(parents=True, exist_ok=True)
    APPS_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)


def seed_bundled_apps() -> None:
    """每次启动时把随仓库自带的示例小程序同步到 ~/.miniapp/apps。"""
    ensure_directories()
    if not BUNDLED_APPS_DIR.is_dir():
        return
    for src in BUNDLED_APPS_DIR.iterdir():
        if not src.is_dir():
            continue
        dst = APPS_DIR / src.name
        if dst.is_symlink():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def _fill_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> bool:
    """把 defaults 中缺失的键补进 target(递归,不覆盖已有值)。返回是否有改动。"""
    changed = False
    for key, dval in defaults.items():
        if key not in target:
            target[key] = json.loads(json.dumps(dval))
            changed = True
        elif isinstance(dval, dict) and isinstance(target.get(key), dict):
            if _fill_missing(target[key], dval):
                changed = True
    return changed


def load_config() -> Dict[str, Any]:
    ensure_directories()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    # 非破坏性补齐新增的默认键(如 memory / thinking_level),保留用户已设的值
    if _fill_missing(config, DEFAULT_CONFIG):
        save_config(config)
    return config


def save_config(config: Dict[str, Any]) -> None:
    ensure_directories()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def update_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    config = load_config()
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    save_config(config)
    return config


def get_llm_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config is None:
        config = load_config()
    return config.get("llm", DEFAULT_CONFIG["llm"])


def get_agent_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config is None:
        config = load_config()
    return config.get("agent", DEFAULT_CONFIG["agent"])


def get_memory_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config is None:
        config = load_config()
    return config.get("memory", DEFAULT_CONFIG["memory"])


def get_asr_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config is None:
        config = load_config()
    return config.get("asr", DEFAULT_CONFIG["asr"])
