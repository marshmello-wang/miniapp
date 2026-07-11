#!/usr/bin/env python3
"""占卜师出题 CLI：读取 MINIAPP_ARGS 中的题目数据，输出 structuredContent。

Agent 调用示例：
  MINIAPP_ARGS='{"text":"你更看重什么？","type":"choice","options":["A","B"]}' python3 scripts/show_question.py

MINIAPP_ARGS JSON 字段：
  text    (str)  题目文字
  type    (str)  "choice" | "open"
  options (list) 选项列表（仅 choice）
"""
import json
import os
import sys


def main():
    raw = os.environ.get("MINIAPP_ARGS", "{}")
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid MINIAPP_ARGS JSON"}))
        sys.exit(1)

    text = args.get("text", "")
    q_type = args.get("type", "open")
    options = args.get("options", [])

    if not text:
        print(json.dumps({"error": "missing question text"}))
        sys.exit(1)

    question = {
        "text": text,
        "type": q_type,
    }
    if q_type == "choice" and options:
        question["options"] = options

    output = {
        "structuredContent": {
            "phase": "question",
            "question": question,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
