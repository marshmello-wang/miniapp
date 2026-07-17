import unittest

from miniapp_demo.backend.conversations.context_builder import (
    build_turn_context,
    compose_runtime_context_message,
    compose_user_message,
)


class ContextBuilderTests(unittest.TestCase):
    def test_no_ui_omits_runtime_context(self):
        turn = build_turn_context(user_intent="查询订单 1042")
        self.assertEqual(compose_user_message(turn), "查询订单 1042")
        self.assertIsNone(compose_runtime_context_message(turn))

    def test_with_ui_includes_yaml_without_wrappers(self):
        turn = build_turn_context(
            user_intent="批准当前订单",
            business_context={
                "skillId": "order-review",
                "uiInstanceId": "ui_123",
                "route": "/orders/1042",
                "revision": 19,
                "view": {"selected_order_id": "1042"},
                "business": {
                    "order": {"id": "1042", "status": "pending"},
                    "allowed_actions": ["approve", "reject"],
                },
            },
        )
        runtime = compose_runtime_context_message(turn)
        self.assertIsNotNone(runtime)
        self.assertIn("context_version: 1", runtime)
        self.assertIn("skill_id: order-review", runtime)
        self.assertIn("selected_order_id: 1042", runtime)
        self.assertIn("status: pending", runtime)
        self.assertNotIn("[USER_INTENT]", compose_user_message(turn))
        self.assertNotIn("[RUNTIME_UI_CONTEXT]", runtime or "")
        self.assertNotIn("active_ui: null", runtime or "")


if __name__ == "__main__":
    unittest.main()
