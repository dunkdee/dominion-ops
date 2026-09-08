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
        path = self._routes_file([{
            "name": "disabled-frontier", "provider": "openai_compatible",
            "base_url": "https://example.invalid", "model": "frontier",
            "enabled": False, "priority": 1, "tasks": ["general"],
            "allow_unauthenticated": True,
        }])
        with mock.patch.object(model_gateway, "_post_json") as post:
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertIsNone(result)
        post.assert_not_called()

    def test_task_specific_route_wins_over_general_fallback_even_with_lower_priority_general(self) -> None:
        path = self._routes_file([
            {
                "name": "general-route", "provider": "openai_compatible",
                "base_url": "https://general.example", "model": "general",
                "enabled": True, "priority": 1, "tasks": ["general"],
                "allow_unauthenticated": True,
            },
            {
                "name": "coding-route", "provider": "openai_compatible",
                "base_url": "https://coding.example", "model": "coder",
                "enabled": True, "priority": 50, "tasks": ["coding"],
                "allow_unauthenticated": True,
            },
        ])
        with mock.patch.object(model_gateway, "_post_json", return_value={
            "choices": [{"message": {"content": "coded"}}]
        }) as post:
            result = model_gateway.route_model("fix it", "ctx", "system", task="coding", routes_file=path)
        self.assertEqual(result["route"], "coding-route")
        self.assertEqual(post.call_count, 1)
        self.assertIn("https://coding.example/v1/chat/completions", post.call_args.args[0])

    def test_provider_failure_falls_through_to_next_approved_route(self) -> None:
        path = self._routes_file([
            {
                "name": "first", "provider": "openai_compatible",
                "base_url": "https://first.example", "model": "first",
                "enabled": True, "priority": 1, "tasks": ["general"],
                "allow_unauthenticated": True,
            },
            {
                "name": "second", "provider": "openai_compatible",
                "base_url": "https://second.example", "model": "second",
                "enabled": True, "priority": 2, "tasks": ["general"],
                "allow_unauthenticated": True,
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

    def test_external_openai_compatible_route_fails_closed_without_auth(self) -> None:
        path = self._routes_file([{
            "name": "external", "provider": "openai_compatible",
            "base_url": "https://external.example", "model": "m",
            "enabled": True, "priority": 1, "tasks": ["general"],
        }])
        with mock.patch.object(model_gateway, "_post_json") as post:
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertIsNone(result)
        post.assert_not_called()

    def test_anthropic_route_fails_closed_without_secret(self) -> None:
        path = self._routes_file([{
            "name": "anthropic", "provider": "anthropic",
            "base_url": "https://api.anthropic.com", "model": "claude-fable-5-1",
            "enabled": True, "priority": 1, "tasks": ["general"],
            "api_key_env": "TEST_ANTHROPIC_KEY_MISSING",
        }])
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(model_gateway, "_post_json") as post:
            os.environ.pop("TEST_ANTHROPIC_KEY_MISSING", None)
            result = model_gateway.route_model("hello", "", "system", routes_file=path)
        self.assertIsNone(result)
        post.assert_not_called()

    def test_router_base_and_model_can_be_injected_from_environment(self) -> None:
        path = self._routes_file([{
            "name": "dominion-router-model", "provider": "openai_compatible",
            "base_url_env": "TEST_DOMINION_ROUTER_BASE", "model_env": "TEST_DOMINION_MODEL",
            "enabled": True, "priority": 1, "tasks": ["research"],
            "api_key_env": "TEST_DOMINION_ROUTER_KEY",
        }])
        env = {
            "TEST_DOMINION_ROUTER_BASE": "https://router.example",
            "TEST_DOMINION_MODEL": "model-x",
            "TEST_DOMINION_ROUTER_KEY": "secret-value",
        }
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(model_gateway, "_post_json", return_value={
            "choices": [{"message": {"content": "researched"}}]
        }) as post:
            result = model_gateway.route_model("research", "", "system", task="research", routes_file=path)
        self.assertEqual(result["model"], "model-x")
        self.assertIn("https://router.example/v1/chat/completions", post.call_args.args[0])
        self.assertEqual(post.call_args.args[2]["Authorization"], "Bearer secret-value")


if __name__ == "__main__":
    unittest.main()
