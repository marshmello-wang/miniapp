# 订单审核助手

这是一个订单审核小程序的后端技能。业务数据(订单)存放在环境变量 `MINIAPP_STORE` 指向的目录下的 `orders.json`。

## 可用脚本

- `python3 scripts/query.py`:读取并返回当前所有订单及统计(读 `$MINIAPP_STORE/orders.json`)。
- `python3 scripts/mutate.py`:批准某订单,入参通过环境变量 `MINIAPP_ARGS`(JSON,如 `{"orderId":"O-1001"}`)。

## 当用户请求"分析风险 / 给建议"时的工作流

1. 先用 `bash` 运行 `python3 scripts/query.py`,拿到当前订单列表(注意 `risk` 与 `amount` 字段)。
2. 基于订单的金额、风险等级、状态,给出简明的风险分析与审批建议(高风险/大额优先人工复核)。
3. 调用 `app_emit` 工具,把结论推送到界面。使用如下 `structuredContent` 结构(界面会与现有数据合并):

```json
{
  "structuredContent": {
    "aiAnalysis": "……你的分析与建议(纯文本或简单 markdown)……"
  }
}
```

保持结论简洁、可执行。不要臆造订单里没有的数据。
