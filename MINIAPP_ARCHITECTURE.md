# MiniApp 技术架构图

## 1. 系统分层

```mermaid
flowchart TB
    subgraph presentation ["L1 产品入口"]
        direction LR
        Chat["Chat"]
        Workbench["Workbench"]
        Standalone["Standalone"]
    end

    subgraph client ["L2 客户端 Runtime"]
        direction LR
        Host["Host Runtime"]
        Bridge["HostBridge"]
        Widget["iframe Widget + miniapp.js"]
        Host --> Bridge
        Bridge <--> Widget
    end

    subgraph backend ["L3 后端 Runtime"]
        direction LR
        Gateway["RuntimeRouter"]
        AppEngine["MiniAppEngine"]
        ChatEngine["ChatEngine"]
        Protocol["Protocol Adapter"]
        Gateway --> AppEngine
        Gateway --> ChatEngine
        AppEngine --> Protocol
        ChatEngine --> Protocol
    end

    subgraph execution ["L4 执行与状态"]
        direction LR
        Agent["ReactAgent + LLM"]
        Sandbox["Sandbox Scripts"]
        MessageStore["MessageStore"]
        BusinessStore["Business Store"]
    end

    subgraph package ["L5 MiniApp 应用包"]
        direction LR
        Manifest["app.yaml"]
        Skill["SKILL.md"]
        Scripts["scripts"]
        UI["assets/ui"]
    end

    presentation --> Host
    Bridge <-->|"POST + SSE per Action"| Gateway
    AppEngine --> Agent
    AppEngine --> Sandbox
    ChatEngine --> Agent
    Agent --> MessageStore
    Sandbox --> BusinessStore

    Manifest -.-> AppEngine
    Skill -.-> Agent
    Scripts -.-> Sandbox
    UI -.-> Widget
```

### 分层含义

| 层级 | 主要职责 |
|---|---|
| L1 产品入口 | 提供 Chat、开发工作台和独立页面三种入口 |
| L2 客户端 Runtime | 承载 iframe，并桥接 Widget 与后端 |
| L3 后端 Runtime | 路由请求，编排 Chat 与 MiniApp，统一事件协议 |
| L4 执行与状态 | 执行 Agent 或 Script，保存对话与业务数据 |
| L5 MiniApp 应用包 | 声明领域知识、确定性能力与专用 UI |

## 2. 一次 Action 的运行时序

```mermaid
sequenceDiagram
    box 用户与客户端
        actor User as 用户
        participant Chat as Chat Page
        participant Bridge as HostBridge
        participant Widget as "iframe + miniapp.js"
    end

    box 后端 Runtime
        participant Engine as MiniAppEngine
        participant ChatAgent as Chat Agent
        participant AppAgent as MiniApp Agent
        participant Sandbox as Sandbox
    end

    box MiniApp 应用包
        participant Package as "app.yaml + SKILL.md + assets/ui + scripts"
    end

    Note over User,Package: 阶段 1：先在 Chat 中对话并发现小程序
    User->>Chat: 发送自然语言需求
    Chat->>ChatAgent: chat.send(sessionId, intent)
    ChatAgent-->>Chat: chat.event(text + show_miniapp_entry)
    Chat-->>User: 显示回复与小程序入口

    Note over User,Package: 阶段 2：点击入口，读取应用包并完成初始化
    User->>Chat: 点击小程序入口
    Chat->>Bridge: 创建 Overlay，传入 appId 与 sessionId
    Bridge->>Package: 请求 app.yaml 声明的 entry.ui
    Package-->>Widget: 返回 assets/ui 页面
    Bridge-->>Widget: Runtime 提供 miniapp.js
    Widget->>Bridge: app.init
    Bridge->>Engine: app.init + appId + sessionId → enter_app
    Engine->>Package: 读取 manifest 与 on_init
    Package-->>Engine: App 元信息与 UI URI
    Engine-->>Bridge: app.resource
    Bridge-->>Widget: App 信息、UI 资源与可选 on_init

    Note over User,Package: 阶段 3：执行一轮 direct_action
    User->>Widget: 点击确定性操作
    Widget->>Bridge: app.call(name, args, requestId)
    Bridge->>Engine: app.call + appId + sessionId
    Engine->>Package: 按 app.yaml 定位 scripts/name
    Package-->>Engine: Script 路径与 visibility
    Engine->>Sandbox: run_script(args)
    Sandbox-->>Engine: stdout + miniapp metadata
    Engine-->>Bridge: app.event(ui_update)
    Bridge-->>Widget: onUiUpdate 更新界面
    Engine-->>Bridge: app.event(done)
    Bridge-->>Widget: onDone

    Note over User,Package: 阶段 4：执行一轮 agent_action
    User->>Widget: 输入开放式意图
    Widget->>Bridge: app.agent(intent, focus, env)
    Bridge->>Engine: app.agent + appId + sessionId
    Engine->>Package: 加载 SKILL.md 与 tool bindings
    Package-->>Engine: 领域工作流与工具定义
    Engine->>AppAgent: 启动 ReactAgent + SKILL
    loop ReAct 事件实时流出
        AppAgent-->>Engine: thinking / text / tool_call
        Engine-->>Bridge: app.event(thinking / text / tool_call)
        Bridge-->>Widget: onTrajectory

        opt Agent 调用应用脚本
            AppAgent->>Sandbox: 执行 Tool
            Sandbox-->>AppAgent: stdout + miniapp metadata
            AppAgent-->>Engine: tool_result
            Engine-->>Bridge: app.event(tool_result + ui_update)
            Bridge-->>Widget: onTrajectory / onUiUpdate
        end

        opt Agent 显式更新 UI
            AppAgent-->>Engine: app_emit → ui_update
            Engine-->>Bridge: app.event(ui_update)
            Bridge-->>Widget: onUiUpdate
        end
    end
    AppAgent-->>Engine: done
    Engine-->>Bridge: app.event(done)
    Bridge-->>Widget: onDone

    Note over User,Package: 阶段 5：退出 App，返回 Chat 继续同一会话
    User->>Chat: 关闭 MiniApp Overlay
    Chat->>Engine: exit-session(appId, sessionId)
    Engine-->>Chat: exit-session 完成
    Chat->>Chat: 卸载 iframe 并刷新会话历史
    User->>Chat: 继续发送消息
    Chat->>ChatAgent: chat.send(同一 sessionId)
    ChatAgent-->>Chat: chat.event(包含 MiniApp 上下文的回复)
    Chat-->>User: 连续呈现对话
```

## 3. 两个核心边界

### Widget 与 Host

```text
iframe 内：miniapp.js
    ↕ postMessage
宿主内：HostBridge
```

`miniapp.js` 为小程序提供调用 API；`HostBridge` 负责 session、路由、权限和后端连接。

### Agent 与 UI

```text
Agent / Script
    → miniapp metadata / app_emit
    → ui_update
    → Widget 渲染
```

模型不直接修改 DOM。`structuredContent` 是 Agent、Script 与 UI 之间的稳定契约。脚本通过 `miniapp_runtime.emit_ui()` 写入 Tool Result metadata，而不是把 UI 协议塞进 stdout。
