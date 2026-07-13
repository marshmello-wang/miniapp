#!/usr/bin/env python3
"""list_orders: 读取业务 store 中的订单并更新小程序界面。"""
import json
import os

from miniapp_runtime import emit_ui


def main() -> None:
    store = os.environ["MINIAPP_STORE"]
    path = os.path.join(store, "orders.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_orders = data.get("orders", [])
    args = json.loads(os.environ.get("MINIAPP_ARGS", "{}") or "{}")
    status = args.get("status")
    orders = [o for o in all_orders if o["status"] == status] if status else all_orders

    stats = {
        "total": len(all_orders),
        "pending": sum(1 for o in all_orders if o["status"] == "pending"),
        "approved": sum(1 for o in all_orders if o["status"] == "approved"),
        "amount_pending": sum(o["amount"] for o in all_orders if o["status"] == "pending"),
    }
    emit_ui({"orders": orders, "stats": stats})

    print(f"查询到 {len(orders)} 笔订单（全部订单共 {len(all_orders)} 笔）。")
    for order in orders:
        print(
            f"- {order['id']} | {order['customer']} | 金额 {order['amount']} | "
            f"风险 {order['risk']} | 状态 {order['status']}"
        )


if __name__ == "__main__":
    main()
