# MiniApp 小程序框架

一个基于 POST + SSE 与 React Agent 的小程序框架 Demo，支持在聊天页面中唤起独立小程序（如算命师），具备 AI 对话、工具调用、历史记录等能力。

## 快速开始

### 前置依赖

- Python 3.10+
- Node.js 18+
### 安装

```bash
git clone git@github.com:marshmello-wang/miniapp.git
cd miniapp
./install.sh
```

`install.sh` 会自动创建 Python 虚拟环境、安装后端和前端依赖。

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
└── miniapp_demo/
    ├── common/             # agent framework + LLM 基础设施
    ├── backend/            # FastAPI 后端
    ├── frontend/           # React + Vite 前端
    ├── apps/               # 内置小程序 (如 fortune-teller)
    └── sdk/                # miniapp.js SDK
```
