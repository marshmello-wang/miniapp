#!/usr/bin/env python3
"""approve_order: 批准指定订单,回写业务 store,输出更新后的订单与统计。"""
import json
import os


def main() -> None:
    store = os.environ["MINIAPP_STORE"]
    path = os.path.join(store, "orders.json")
    args = json.loads(os.environ.get("MINIAPP_ARGS", "{}") or "{}")
    order_id = args.get("orderId")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    orders = data.get("orders", [])

    found = False
    for o in orders:
        if o["id"] == order_id:
            o["status"] = "approved"
            found = True
            break

    if found:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    stats = {
        "total": len(orders),
        "pending": sum(1 for o in orders if o["status"] == "pending"),
        "approved": sum(1 for o in orders if o["status"] == "approved"),
        "amount_pending": sum(o["amount"] for o in orders if o["status"] == "pending"),
    }
    print(json.dumps({
        "structuredContent": {
            "orders": orders,
            "stats": stats,
            "lastAction": {"approved": order_id, "ok": found},
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
