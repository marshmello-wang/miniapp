#!/usr/bin/env python3
"""Project fortune-teller view state into business context for the Agent."""
import json
import os
import sys


def main() -> None:
    raw = os.environ.get("MINIAPP_ARGS", "{}")
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        print("错误：MINIAPP_ARGS 不是有效 JSON", file=sys.stderr)
        sys.exit(1)

    view_snapshot = args.get("viewSnapshot") or {}
    env = view_snapshot.get("env") or {}
    business = {
        "app": env.get("app", "fortune-teller"),
        "phase": env.get("phase", "idle"),
    }
    theme = env.get("theme")
    if theme:
        business["theme"] = theme
    current_question = env.get("currentQuestion")
    if current_question:
        business["currentQuestion"] = current_question
    print(json.dumps({"business": business}, ensure_ascii=False))


if __name__ == "__main__":
    main()
