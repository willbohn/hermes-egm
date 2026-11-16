"""The host facade is a unit-test fake here; live execution is checked separately."""

import unittest
from dataclasses import dataclass, field

from hermes_egm import review


@dataclass
class Usage:
    input_tokens: int = 20
    output_tokens: int = 10
    total_tokens: int = 30


@dataclass
class Reply:
    parsed: object = field(default_factory=lambda: {"findings": []})
    provider: str = "test-provider"
    model: str = "test-model"
    usage: Usage = field(default_factory=Usage)


class FakeLlm:
    def __init__(self) -> None:
        self.calls = []

    async def acomplete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return Reply()


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_lens_gets_one_fresh_bounded_tool_free_request(self) -> None:
        self.assertTrue(hasattr(review, "run_review"), "native review runner is missing")
        llm = FakeLlm()
        request = review.ReviewRequest.parse(
            {
                "target": "spec",
                "documents": [{"id": "spec", "text": "Deliver webhooks."}],
            }
        )
        result = await review.run_review(llm, request)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["outcome"], "no_findings")
        self.assertEqual(result["snapshot_id"], request.snapshot_id)
        self.assertEqual(len(llm.calls), 3)
        self.assertEqual(len(result["reviewers"]), 3)
        self.assertEqual(result["findings"], [])
        for call in llm.calls:
            self.assertEqual(
                set(call),
                {
                    "instructions",
                    "input",
                    "json_schema",
                    "schema_name",
                    "system_prompt",
                    "max_tokens",
                    "timeout",
                    "purpose",
                },
            )
            self.assertEqual(call["max_tokens"], 2400)
            self.assertEqual(call["timeout"], 90)
            self.assertEqual(call["input"], [{"type": "text", "text": request.payload()}])
            self.assertNotIn("provider", call)
            self.assertNotIn("model", call)
            self.assertNotIn("tools", call)
        self.assertEqual(result["usage"]["total_tokens"], 90)

    async def test_configured_token_budget_reaches_every_reviewer_request(self) -> None:
        llm = FakeLlm()
        request = review.ReviewRequest.parse(
            {
                "target": "spec",
                "documents": [{"id": "spec", "text": "Deliver webhooks."}],
            }
        )
        result = await review.run_review(llm, request, max_output_tokens=8192)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(llm.calls), 3)
        for call in llm.calls:
            self.assertEqual(call["max_tokens"], 8192)

    async def test_configured_timeout_reaches_every_reviewer_request(self) -> None:
        llm = FakeLlm()
        request = review.ReviewRequest.parse(
            {
                "target": "spec",
                "documents": [{"id": "spec", "text": "Deliver webhooks."}],
            }
        )
        result = await review.run_review(llm, request, timeout_seconds=600)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(llm.calls), 3)
        for call in llm.calls:
            self.assertEqual(call["timeout"], 600)

    async def test_identical_findings_are_merged_without_another_model_call(self) -> None:
        from test_findings import finding, request

        class FindingLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return Reply(parsed={"findings": [finding()]})

        llm = FindingLlm()
        result = await review.run_review(llm, request())
        self.assertEqual(result["outcome"], "findings")
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["lenses"], list(review.LENSES))
        self.assertEqual(len(llm.calls), 3)

    async def test_failure_is_not_a_clean_review_and_exception_payloads_are_not_echoed(
        self,
    ) -> None:
        from test_findings import request

        class FailingLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                if kwargs["purpose"].endswith("design"):
                    raise RuntimeError("SENSITIVE_EXCEPTION_PAYLOAD")
                return Reply()

        result = await review.run_review(FailingLlm(), request())
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertNotIn("SENSITIVE_EXCEPTION_PAYLOAD", str(result))
        self.assertIn("provider_error", str(result))

    async def test_unparseable_response_fails_closed_and_timeout_has_no_retry(self) -> None:
        from test_findings import request

        class InvalidLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["purpose"].endswith("design"):
                    raise TimeoutError()
                return Reply(parsed=None)

        llm = InvalidLlm()
        result = await review.run_review(llm, request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertEqual(len(llm.calls), 3)
        self.assertIn("timeout", str(result))
        self.assertIn("invalid_response", str(result))

    async def test_reviewers_run_concurrently_and_outer_cancellation_propagates(self) -> None:
        import asyncio

        from test_findings import request

        class ConcurrentLlm(FakeLlm):
            def __init__(self):
                super().__init__()
                self.ready = asyncio.Event()

            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 3:
                    self.ready.set()
                await asyncio.wait_for(self.ready.wait(), timeout=1)
                return Reply()

        result = await review.run_review(ConcurrentLlm(), request())
        self.assertEqual(result["status"], "complete")

        class CancelledLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await review.run_review(CancelledLlm(), request())
