"""Exercise the exact public tool handler, including ignored host context."""

import importlib
import importlib.util
import json
import unittest
from pathlib import Path

from test_runner import FakeLlm


class Context:
    def __init__(self, settings=None):
        self.llm = FakeLlm()
        self.tools = {}
        self.skills = {}
        self.settings = dict(settings or {})
        self.sections = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_system_prompt_section(self, identifier, content, **kwargs):
        self.sections[identifier] = content

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs

    def register_skill(self, name, path, description=""):
        self.skills[name] = Path(path)


class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_suggestion_guidance_does_not_make_reviewer_calls(self):
        ctx = Context()
        importlib.import_module("hermes_egm.plugin").register(ctx)
        self.assertIn("hermes-egm.activation", ctx.sections)
        text = ctx.sections["hermes-egm.activation"](
            {
                "session_id": "test-session",
                "cwd": str(Path.cwd()),
            }
        )
        self.assertIn("suggest", text)
        self.assertIn("automatic=false", text)
        self.assertEqual(ctx.llm.calls, [])

    async def test_registration_and_native_handler_use_only_explicit_arguments(self):
        self.assertIsNotNone(
            importlib.util.find_spec("hermes_egm.plugin"), "plugin adapter is missing"
        )
        plugin = importlib.import_module("hermes_egm.plugin")
        ctx = Context()
        plugin.register(ctx)
        self.assertEqual(set(ctx.tools), {"egm_review"})
        self.assertTrue(ctx.tools["egm_review"]["is_async"])
        handler = ctx.tools["egm_review"]["handler"]
        result = json.loads(
            await handler(
                {
                    "target": "spec",
                    "documents": [{"id": "spec", "text": "Review this design."}],
                    "lenses": ["design"],
                },
                parent_agent="PARENT_ONLY_CANARY",
                user_task="PRIVATE_PRIOR_DISCUSSION",
            )
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(ctx.llm.calls), 1)
        self.assertNotIn("PARENT_ONLY_CANARY", str(ctx.llm.calls))
        self.assertNotIn("PRIVATE_PRIOR_DISCUSSION", str(ctx.llm.calls))
        self.assertEqual(len(ctx.skills), 7)
        for path in ctx.skills.values():
            self.assertTrue(path.is_file(), str(path))

    async def test_nonobject_input_returns_invalid_input_without_throwing(self):
        ctx = Context()
        importlib.import_module("hermes_egm.plugin").register(ctx)
        for value in (None, [], "not an object"):
            try:
                result = json.loads(await ctx.tools["egm_review"]["handler"](value))
            except Exception as exc:
                self.fail(f"Malformed input must return invalid_input, not {type(exc).__name__}")
            self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(ctx.llm.calls, [])

    async def test_invalid_input_returns_json_without_spending_model_usage(self):
        self.assertIsNotNone(
            importlib.util.find_spec("hermes_egm.plugin"), "plugin adapter is missing"
        )
        ctx = Context()
        importlib.import_module("hermes_egm.plugin").register(ctx)
        result = json.loads(await ctx.tools["egm_review"]["handler"]({"target": "absent"}))
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(ctx.llm.calls, [])

    async def _run_one_lens(self, settings):
        plugin = importlib.import_module("hermes_egm.plugin")
        ctx = Context(settings=settings)
        plugin.register(ctx)
        result = json.loads(
            await ctx.tools["egm_review"]["handler"](
                {
                    "target": "spec",
                    "documents": [{"id": "spec", "text": "Review this design."}],
                    "lenses": ["design"],
                }
            )
        )
        self.assertEqual(result["status"], "complete")
        return ctx.llm.calls

    async def test_review_timeout_setting_reaches_reviewer_requests(self):
        calls = await self._run_one_lens({"review_timeout_seconds": 600})
        self.assertEqual([call["timeout"] for call in calls], [600.0])

    async def test_invalid_review_timeout_falls_back_to_ninety_seconds(self):
        for bad in (0, 5, 99999, "600", True, None):
            with self.subTest(value=bad):
                calls = await self._run_one_lens({"review_timeout_seconds": bad})
                self.assertEqual([call["timeout"] for call in calls], [90.0])

    async def test_review_max_tokens_setting_reaches_reviewer_requests(self):
        calls = await self._run_one_lens({"review_max_tokens": 8192})
        self.assertEqual([call["max_tokens"] for call in calls], [8192])

    async def test_invalid_review_max_tokens_falls_back_to_2400(self):
        for bad in (0, 100, 99999, "8192", True, None):
            with self.subTest(value=bad):
                calls = await self._run_one_lens({"review_max_tokens": bad})
                self.assertEqual([call["max_tokens"] for call in calls], [2400])
