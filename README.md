# MCP Apps vs AG-UI —— 两个极简 demo

两个零依赖(纯 Python 标准库 + 原生 JS,**无需 pip install**)的可运行 demo,帮你直观理解这两个协议,以及它们和你的三个核心概念的对应关系。

## 你的三个核心概念 → 两个协议里的对应原语

| 你的概念 | MCP Apps | AG-UI |
|---|---|---|
| H5 打包在 skill、渲染给用户 | ✅ `_meta.ui.resourceUri` + `ui://` 资源 + 沙箱 iframe | ❌ 不覆盖(它假设你自己有前端) |
| **normal action**(不过 AI,直连 cli) | ✅ app 直接发 `tools/call` | ⚠️ 弱(要靠 CustomEvent 硬凑) |
| **ai action**(payload 进对话交 agent) | ✅ `ui/message` | ✅ 发起一次 run |
| **UI 现状作 context** | ✅ `ui/update-model-context` | ✅ Shared State(agent 可读) |
| cli 改前端(状态驱动下行) | ⚠️ 只能按工具结果整块刷新 | ✅✅ `STATE_SNAPSHOT` + `STATE_DELTA`(JSON Patch) |
| 流式 / 长任务 | 一般 | ✅✅ 天生流式 |

一句话:**MCP Apps 覆盖"UI 容器"这一半,AG-UI 覆盖"事件流 + 状态同步"这一半;两者都缺"两级 action 分类 + 统一历史"这个你自己的内核。**

## 怎么跑

两个 demo 各自独立,端口不同,可同时开。

```bash
# 终端 1
python3 ag_ui_demo/server.py        # -> http://localhost:8765

# 终端 2
python3 mcp_apps_demo/server.py     # -> http://localhost:8766
```

然后浏览器分别打开这两个地址。

## 建议观察顺序

### AG-UI demo（http://localhost:8765）
1. 输入框里打一个任务(比如"买牛奶")回车 —— 这是一次 **ai action**。
2. **左栏**看后端推来的原始事件流:`RUN_STARTED → STATE_SNAPSHOT → TEXT_MESSAGE_* → TOOL_CALL_* → STATE_DELTA → RUN_FINISHED`。
3. **右栏**看这些事件"作用出的结果":助手文本逐字出现、todo 列表被 `STATE_DELTA` 增量更新。
4. 重点体会:**前端不写业务胶水,只按标准事件类型渲染**;状态靠 snapshot/delta 同步。

### MCP Apps demo（http://localhost:8766）
1. 这个页面本身就是 **Host(宿主)**;右边白框里是跑在**沙箱 iframe**里的 skill UI。
2. 点 `+1 (tools/call)` —— 这是 **normal action**:UI 直接调后端工具,不经过 AI;看左栏 JSON-RPC 流水。
3. 点 `上报现状` —— 这是 **UI 现状作 context**:UI 状态被写进 Host 的 "Model Context" 面板。
4. 底部输入框问 agent —— 这是 **ai action**:消息被投进 Host 的 "Conversation" 面板。
5. 重点体会:**app 和 host 完全隔离**,只通过 postMessage 上的 JSON-RPC 通信;三个概念对应三种 `ui/*` 消息。

## 各 demo 的文件

- `ag_ui_demo/server.py` — SSE 事件流后端(一个模拟 agent)
- `ag_ui_demo/index.html` — 消费事件流 + 应用 JSON Patch 的前端
- `mcp_apps_demo/server.py` — 扮演 MCP server:工具清单 / ui:// 资源 / tools/call
- `mcp_apps_demo/host.html` — 扮演 Host:渲染沙箱 iframe + JSON-RPC 桥
- `mcp_apps_demo/widget.html` — 跑在沙箱里的 skill UI(app)
