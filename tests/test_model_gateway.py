from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

COMMAND_CENTER = Path(__file__).resolve().parents[1] / "apps" / "command-center"
if str(COMMAND_CENTER) not in sys.path:
    sys.path.insert(0, str(COMMAND_CENTER))

import model_gateway  # noqa: E402


class ModelGatewayTests(unittest.TestCase):
    def _routes_file(self, routes: list[dict]) -> str:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        json.dump({"routes": routes}, handle)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_disabled_route_is_never_called(self) -> None:
        path = self._routes_file([
            {
                "name": "disabled-frontier",
                "provider": "openai_compatible",
                "base_url": "https://example.invalid",
                "model": "frontier",
                "enabled": False,
                "priority": 1,
                "tasks": ["general"],
            }
        ])
        with mock.patch.object(model_gateway, "_post_json") as post:
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertIsNone(result)
        post.assert_not_called()

    def test_task_specific_route_wins_over_general_fallback(self) -> None:
        path = self._routes_file([
            {
                "name": "coding-route",
                "provider": "openai_compatible",
                "base_url": "https://coding.example",
                "model": "coder",
                "enabled": True,
                "priority": 5,
                "tasks": ["coding"],
            },
            {
                "name": "general-route",
                "provider": "openai_compatible",
                "base_url": "https://general.example",
                "model": "general",
                "enabled": True,
                "priority": 10,
                "tasks": ["general"],
            },
        ])
        with mock.patch.object(model_gateway, "_post_json", return_value={
            "choices": [{"message": {"content": "coded"}}]
        }) as post:
            result = model_gateway.route_model("fix it", "ctx", "system", task="coding", routes_file=path)
        self.assertEqual(result["route"], "coding-route")
        self.assertEqual(result["model"], "coder")
        self.assertEqual(post.call_count, 1)
        self.assertIn("https://coding.example/v1/chat/completions", post.call_args.args[0])

    def test_provider_failure_falls_through_to_next_approved_route(self) -> None:
        path = self._routes_file([
            {
                "name": "first",
                "provider": "openai_compatible",
                "base_url": "https://first.example",
                "model": "first",
                "enabled": True,
                "priority": 1,
                "tasks": ["general"],
            },
            {
                "name": "second",
                "provider": "openai_compatible",
                "base_url": "https://second.example",
                "model": "second",
                "enabled": True,
                "priority": 2,
                "tasks": ["general"],
            },
        ])

        def fake_post(url, payload, headers, timeout):
            if "first.example" in url:
                raise ValueError("provider failure")
            return {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.object(model_gateway, "_post_json", side_effect=fake_post):
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertEqual(result["route"], "second")
        self.assertEqual(result["answer"], "ok")

    def test_anthropic_route_fails_closed_without_secret(self) -> None:
        path = self._routes_file([
            {
                "name": "anthropic",
                "provider": "anthropic",
                "base_url": "https://api.anthropic.com",
                "model": "claude-fable-5-1",
                "enabled": True,
                "priority": 1,
                "tasks": ["general"],
                "api_key_env": "TEST_ANTHROPIC_KEY_MISSING",
            }
        ])
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(model_gateway, "_post_json") as post:
            os.environ.pop("TEST_ANTHROPIC_KEY_MISSING", None)
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertIsNone(result)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
