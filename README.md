# MiniApp 小程序框架

一个基于 WebSocket + React Agent 的小程序框架 Demo，支持在聊天页面中唤起独立小程序（如算命师），具备 AI 对话、工具调用、历史记录等能力。

## 快速开始

### 前置依赖

- Python 3.10+
- Node.js 18+
- Git

### 安装

```bash
git clone git@github.com:marshmello-wang/miniapp.git
cd miniapp
./install.sh
```

`install.sh` 会自动：
1. 克隆 `forge_os`（agent framework 依赖）
2. 创建 Python 虚拟环境并安装依赖
3. 安装前端 npm 依赖

### 配置

编辑 `~/.miniapp/config.json`，设置你的 LLM provider 和 api_key。

### 运行

```bash
./run.sh
```

打开 http://localhost:3790 即可。

## 项目结构

```
miniapp/
├── install.sh              # 安装脚本
├── run.sh                  # 启动脚本
├── forge_os/               # (自动克隆) agent framework 依赖
└── miniapp_demo/
    ├── backend/            # FastAPI 后端
    ├── frontend/           # React + Vite 前端
    ├── apps/               # 内置小程序 (如 fortune-teller)
    └── sdk/                # oneagent.js SDK
```
