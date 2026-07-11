#!/usr/bin/env python3
"""list_orders: 读取业务 store 中的订单,输出 structuredContent。"""
import json
import os


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
    print(json.dumps({"structuredContent": {"orders": orders, "stats": stats}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
