# 小程序框架 Demo (app-skill v0.3)

以 [`agent_framework`](../../forge_os/common/agent_framework) 为底座、[app-skill v0.3 协议](../app-skill-protocol-v0.3.md) 为规范的小程序框架 demo。

一个「小程序」= 一个 Skill 包(`app.yaml` + `SKILL.md` + `scripts/` + `assets/ui` + `assets/schema`)。
用户在前端点开小程序,右侧用 iframe 渲染它的 H5 界面;界面既能发 **direct_action**(不经过 AI,直接在 sandbox 跑脚本),也能发 **agent_action**(把意图 + 界面状态交给真实 LLM 决策)。

## 架构

```
前端 React(客户端运行时 Host)         后端 FastAPI(小程序引擎)
┌─────────────┬───────────────┐        ┌───────────────────────────┐
│ 小程序列表   │  iframe/编辑器 │        │ runtime_router POST+SSE   │
│ AppList     │  AppFrame      │  POST  │ runtime_service 请求调度  │
│ 编辑器       │  SkillEditor   │──────► │ engine      会话/路由/协议  │
│ Debug 面板   │  DebugPanel    │  SSE   │ sandbox     本地脚本执行    │
│ Host Bridge (postMessage↔HTTP)│◄────── │ agent_runner ReactAgent    │
└─────────────┴───────────────┘        │ stores  MessageStore+业务   │
                                       └───────────────────────────┘
```

- **direct_action**:`POST app.call{name,args}` → 引擎按 `app.yaml.scripts[]` 找到脚本 → sandbox 子进程执行 → 响应流返回 `ui_update*` + `done`。
- **agent_action**:`POST app.agent{intent,focus,env}` → 引擎读历史 + 注入界面状态 → `ReactAgent`(真 LLM,带 `bash` 和 `app_emit` 工具)→ 同一响应流返回 `thinking/text/tool_call/tool_result/ui_update/done`。
- **脚本 UI 更新**:应用脚本通过 `miniapp_runtime.emit_ui()` 写入 `MINIAPP_RESULT_PATH` 临时结果文件;Runtime 在 Bash 完成后读取 metadata,转成 `ui_update`;stdout 仅作为普通工具输出。
- **app_emit**:agent 调用该工具即产生 `ui_update`(把 `structuredContent` 推到界面)。

## 目录

```
miniapp_demo/
├── backend/           FastAPI 引擎(config/registry/stores/sandbox/protocol/runner/engine/runtime/routers)
├── script_sdk/        脚本侧 metadata SDK(miniapp_runtime.py)
├── sdk/miniapp.js    widget 侧 Bridge SDK(iframe 内引入)
├── apps/order-review/ 种子示例小程序
└── frontend/          Vite + React + TS(三栏:列表 / iframe·编辑器 / Debug)
```

运行时数据在 `~/.miniapp/`:`config.json`(LLM 配置)、`messages.db`(agent 消息)、`apps/`(已安装小程序)、`sessions/`(每 session 业务 store)。

## 运行

```bash
cd miniapp_demo
./run.sh          # 后端 :8790,前端 :3790
```

首次会自动:创建 Python venv(`.venv`,需要 `python3.12`)、拷贝种子小程序到 `~/.miniapp/apps`、安装前端依赖。
打开 http://localhost:3790 。

> 手动分别启动:
> ```bash
> # 后端
> FORGE_OS_ROOT=/path/to/forge_os .venv/bin/python -m uvicorn miniapp_demo.backend.main:app --port 8790   # 在含 miniapp_demo 的目录运行
> # 前端
> cd frontend && npm install && npm run dev -- --port 3790
> ```

## 配置 LLM

`agent_action` 使用真实 LLM,接入方式与 `lite_code` **完全一致**:

- 配置结构与 lite_code 相同:`~/.miniapp/config.json` 含 `llm` / `agent` / `memory` 三段(默认值也对齐 lite_code)。
- Agent 装配复用 lite_code 的做法:`LLMClient` + `ToolRegistry`(bash / text_edit / read_file / list_files / grep_search)+ `MemoryConfig`(L1/L2 折叠)+ `DefaultContextStrategy` + `OrchestratorAgent` 图 + `run_task`;`read_file/list_files/grep_search` 与系统提示词直接复用 lite_code 的模块。
- 小程序特有增量:bash 的 cwd=小程序目录并注入 `MINIAPP_STORE`;额外注册 `app_emit` 工具;按小程序 skill 构建 `SkillConfig`;mini-app 说明经 `get_system_prompt(extra_context=...)` 注入。

首次在前端「设置」里填写 provider / model / API Key 即可。`direct_action` 不需要 LLM。

## 试用(order-review)

1. 左栏点「订单审核」→ 中间 iframe 渲染,自动 `list_orders`(direct)拉出订单。
2. 点某行「批准」→ Debug 面板出现 `app.call → ui_update → done`,列表实时更新。
3. 输入「分析当前订单风险」点「AI 分析」→ Debug 出现 `thinking/tool_call/tool_result/ui_update/done` 流式,界面显示 AI 结论。
4. 点「编辑技能文件」→ 拖拽上传 / 拖拽移动 / 编辑文本 / 预览图片。
5. 「新建」可脚手架一个新的小程序。

## 协议要点(v0.3)

| 方向 | 帧 | 说明 |
| --- | --- | --- |
| 上行 | `POST /api/runtime/actions` | `app.init` / `app.call` / `app.agent` / `chat.send` |
| 上行 | `POST /api/runtime/actions/{requestId}/cancel` | 取消仍在执行的 Action |
| 下行 | 同一 POST 的 `text/event-stream` | `app.resource` / `app.event` / `chat.event` 直到 `done` |

本 demo 为 MVP:单用户 `local`,`ui_update` 走全量(界面侧做字段合并),未做安全护栏 / 增量 patch / 断线续传。
