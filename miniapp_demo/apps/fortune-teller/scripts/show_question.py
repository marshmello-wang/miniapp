#!/usr/bin/env python3
"""占卜师出题 CLI：读取 MINIAPP_ARGS 中的题目数据并更新小程序界面。

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

from miniapp_runtime import emit_ui, end_turn


def main():
    raw = os.environ.get("MINIAPP_ARGS", "{}")
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        print("错误：MINIAPP_ARGS 不是有效 JSON。正确用法：", file=sys.stderr)
        print("  MINIAPP_ARGS='{\"text\":\"问题内容\",\"type\":\"choice\",\"options\":[\"A\",\"B\"]}' python3 fortune-teller/scripts/show_question.py", file=sys.stderr)
        sys.exit(1)

    text = args.get("text", "")
    q_type = args.get("type", "open")
    options = args.get("options", [])

    if not text:
        print("错误：缺少题目文字。正确用法：", file=sys.stderr)
        print("  MINIAPP_ARGS='{\"text\":\"问题内容\",\"type\":\"choice\",\"options\":[\"A\",\"B\"]}' python3 fortune-teller/scripts/show_question.py", file=sys.stderr)
        sys.exit(1)

    question = {
        "text": text,
        "type": q_type,
    }
    if q_type == "choice" and options:
        question["options"] = options

    emit_ui({"phase": "question", "question": question})
    end_turn()
    print(f"已向界面展示题目：{text}")


if __name__ == "__main__":
    main()
