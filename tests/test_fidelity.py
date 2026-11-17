"""Synthetic offline checks for lens scope and bounded comprehension output."""

import json
import unittest
from copy import deepcopy
from dataclasses import replace

from test_findings import finding, request
from test_plugin import Context
from test_runner import FakeLlm, Reply

from hermes_egm import review
from hermes_egm.plugin import register


class ComprehensionLlm(FakeLlm):
    def __init__(self, parsed):
        super().__init__()
        self.parsed = parsed

    async def acomplete_structured(self, **kwargs):
        class UninspectedReply(Reply):
            @property
            def text(self):
                raise AssertionError("RAW_REPLY_MUST_NOT_BE_READ")

        self.calls.append(kwargs)
        return UninspectedReply(
            parsed=self.parsed
            if kwargs["purpose"].endswith("comprehension")
            else {"findings": [finding()]}
        )


class FidelityTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_paraphrase_rejects_the_whole_response(self):
        cases = [
            None,
            [],
            "REJECTED_PARAPHRASE_CANARY",
            {},
            {"findings": [finding()]},
            {"paraphrase": "REJECTED_PARAPHRASE_CANARY"},
            {"paraphrase": "REJECTED_PARAPHRASE_CANARY", "findings": [], "extra": True},
            {"paraphrase": "REJECTED_PARAPHRASE_CANARY", "findings": None},
        ]
        cases += [
            {"paraphrase": value, "findings": [finding()]}
            for value in (
                None,
                False,
                42,
                [],
                {},
                "",
                " \n\t",
                "x" * 1201,
                "é" * 1201,
            )
        ]
        for parsed in cases:
            for lenses in (("comprehension",), review.LENSES):
                with self.subTest(parsed=parsed, lenses=lenses):
                    llm = ComprehensionLlm(parsed)
                    result = await review.run_review(llm, replace(request(), lenses=lenses))
                    failed = result["reviewers"][0]
                    self.assertEqual(failed["status"], "failed")
                    self.assertEqual(failed["findings"], [])
                    self.assertIsNone(failed["paraphrase"])
                    self.assertEqual(
                        failed["validation_error"],
                        "parsed_unavailable" if parsed is None else "schema_invalid",
                    )
                    self.assertTrue(failed["error"].startswith("invalid_response:"))
                    self.assertEqual(result["outcome"], "incomplete")
                    self.assertEqual(result["status"], "failed" if len(lenses) == 1 else "partial")
                    self.assertEqual(
                        result["findings"],
                        []
                        if len(lenses) == 1
                        else [{**finding(), "lenses": ["design", "readiness"]}],
                    )
                    self.assertEqual(len(llm.calls), len(lenses))
                    self.assertEqual(result["usage"]["total_tokens"], 30 * len(lenses))
                    self.assertNotIn("REJECTED_PARAPHRASE_CANARY", json.dumps(result))

    async def test_paraphrase_character_boundaries_accept_without_rewriting(self):
        for paraphrase in ("x", "x" * 1200, "é" * 1200, "  A webhook design.\n"):
            with self.subTest(length=len(paraphrase)):
                parsed = {"paraphrase": paraphrase, "findings": []}
                before = deepcopy(parsed)
                llm = ComprehensionLlm(parsed)
                result = await review.run_review(llm, replace(request(), lenses=("comprehension",)))
                self.assertEqual(result["status"], "complete")
                self.assertEqual(result["outcome"], "no_findings")
                self.assertEqual(result["reviewers"][0]["paraphrase"], paraphrase)
                self.assertIsNone(result["reviewers"][0]["validation_error"])
                self.assertEqual(parsed, before)
                self.assertEqual(len(llm.calls), 1)

    async def test_bad_citations_discard_valid_paraphrase_and_all_findings(self):
        req = replace(
            request(),
            documents=(*request().documents, review.Document("worker.py", "CODE_ONLY_CANARY")),
            lenses=("comprehension", "design", "readiness"),
        )
        for changes, code in (
            ({"document": "worker.py", "line": 1, "quote": "CODE_ONLY_CANARY"}, "unknown_document"),
            ({"line": 0}, "line_out_of_range"),
            ({"line": 3}, "line_out_of_range"),
            ({"line": True}, "schema_invalid"),
            ({"quote": "REJECTED_QUOTE_CANARY"}, "quote_mismatch"),
        ):
            with self.subTest(code=code, changes=changes):
                invalid = finding()
                invalid["evidence"][0].update(changes)
                parsed = {
                    "paraphrase": "REJECTED_PARAPHRASE_CANARY",
                    "findings": [finding(), invalid],
                }
                before = deepcopy(parsed)
                llm = ComprehensionLlm(parsed)
                result = await review.run_review(llm, req)
                failed = result["reviewers"][0]
                self.assertEqual(failed["validation_error"], code)
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["findings"], [])
                self.assertIsNone(failed["paraphrase"])
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["outcome"], "incomplete")
                self.assertEqual(
                    result["findings"], [{**finding(), "lenses": ["design", "readiness"]}]
                )
                self.assertEqual(parsed, before)
                self.assertEqual(len(llm.calls), 3)
                self.assertNotIn("REJECTED_", json.dumps(result))

    async def test_other_lenses_keep_findings_only_output_validation(self):
        class ExtraFieldLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return Reply(parsed={"findings": [finding()], "paraphrase": "UNEXPECTED_CANARY"})

        for lens in ("design", "readiness"):
            with self.subTest(lens=lens):
                llm = ExtraFieldLlm()
                result = await review.run_review(llm, replace(request(), lenses=(lens,)))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["outcome"], "incomplete")
                self.assertEqual(result["findings"], [])
                self.assertIsNone(result["reviewers"][0]["paraphrase"])
                self.assertEqual(result["reviewers"][0]["validation_error"], "schema_invalid")
                self.assertNotIn("UNEXPECTED_CANARY", json.dumps(result))

    async def test_comprehension_host_errors_do_not_become_validation_diagnostics(self):
        class FailingLlm(FakeLlm):
            def __init__(self, error):
                super().__init__()
                self.error = error

            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                raise self.error

        for error, category in (
            (TimeoutError("PRIVATE_ERROR_CANARY"), "timeout:"),
            (ValueError("PRIVATE_ERROR_CANARY"), "provider_error:"),
            (review.InvalidReview("PRIVATE_ERROR_CANARY"), "provider_error:"),
        ):
            with self.subTest(category=category, error=type(error).__name__):
                llm = FailingLlm(error)
                result = await review.run_review(llm, replace(request(), lenses=("comprehension",)))
                failed = result["reviewers"][0]
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["outcome"], "incomplete")
                self.assertTrue(failed["error"].startswith(category))
                self.assertIsNone(failed["validation_error"])
                self.assertIsNone(failed["paraphrase"])
                self.assertEqual(failed["findings"], [])
                self.assertEqual(len(llm.calls), 1)
                self.assertNotIn("PRIVATE_ERROR_CANARY", json.dumps(result))

    async def test_requests_state_explicit_lens_criteria(self):
        llm = FakeLlm()
        await review.run_review(llm, request())
        instructions = {call["purpose"].split(".")[-1]: call["instructions"] for call in llm.calls}
        criteria = {
            "comprehension": (
                "self-containment",
                "only the target document",
                "paraphrase",
                "2–4 sentences",
                "1200 characters",
                "undefined terms",
                "contradictions",
                "unstated assumptions",
            ),
            "design": (
                "simplicity",
                "alternatives",
                "trade-offs",
                "risks",
                "mitigations",
                "trust-boundary",
            ),
            "readiness": (
                "implementation decisions",
                "interfaces",
                "data flow",
                "ownership",
                "failure handling",
                "testable acceptance criteria",
                "unresolved choices",
            ),
        }
        for lens, terms in criteria.items():
            for term in terms:
                with self.subTest(lens=lens, term=term):
                    self.assertIn(term, instructions[lens].lower())

    def test_comprehension_citations_are_limited_to_the_target(self):
        req = review.ReviewRequest.parse(
            {
                "target": "spec",
                "documents": [
                    {"id": "spec", "text": "# Design\nDeliver webhooks."},
                    {"id": "worker.py", "text": "CODE_ONLY_CANARY"},
                ],
            }
        )
        item = finding()
        item["evidence"] = [{"document": "worker.py", "line": 1, "quote": "CODE_ONLY_CANARY"}]
        raw = {"paraphrase": "The design proposes webhooks.", "findings": [finding(), item]}
        before = deepcopy(raw)
        with self.assertRaises(review.InvalidReview) as raised:
            review.validate_findings(raw, req, "comprehension")
        self.assertEqual(raised.exception.code, "unknown_document")
        self.assertEqual(raw, before)
        for lens in ("design", "readiness"):
            self.assertEqual(
                review.validate_findings({"findings": [item]}, req, lens),
                [{**item, "lenses": [lens]}],
            )
        self.assertEqual(len(req.documents), 2)

    async def test_paraphrase_is_additive_and_does_not_change_findings(self):
        paraphrase = "PARAPHRASE_ONLY_CANARY: The design proposes delivering webhooks."
        response = {"paraphrase": paraphrase, "findings": [finding()]}
        before = deepcopy(response)

        class FixtureLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return Reply(
                    parsed=response
                    if kwargs["purpose"].endswith("comprehension")
                    else {"findings": [finding()]}
                )

        ctx = Context()
        ctx.llm = FixtureLlm()
        register(ctx)
        req = request()
        result = json.loads(
            await ctx.tools["egm_review"]["handler"](
                {
                    "target": req.target,
                    "documents": [{"id": doc.id, "text": doc.text} for doc in req.documents],
                }
            )
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["outcome"], "findings")
        self.assertIs(result["automatic"], False)
        self.assertEqual(result["snapshot_id"], req.snapshot_id)
        self.assertEqual(result["findings"], [{**finding(), "lenses": list(review.LENSES)}])
        for report, call in zip(result["reviewers"], ctx.llm.calls, strict=True):
            self.assertEqual(report["findings"], [{**finding(), "lenses": [report["lens"]]}])
            self.assertEqual(
                report["paraphrase"], paraphrase if report["lens"] == "comprehension" else None
            )
            self.assertIsNone(report["validation_error"])
            self.assertNotIn("PARAPHRASE_ONLY_CANARY", json.dumps(call))
            if report["lens"] == "comprehension":
                schema = call["json_schema"]
                self.assertEqual(set(schema["required"]), {"paraphrase", "findings"})
                self.assertEqual(set(schema["properties"]), {"paraphrase", "findings"})
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(
                    schema["properties"]["paraphrase"],
                    {"type": "string", "minLength": 1, "maxLength": 1200},
                )
            else:
                self.assertEqual(call["json_schema"], review.FINDINGS_SCHEMA)
                self.assertEqual(call["schema_name"], "egm_findings")
        self.assertEqual(response, before)
        self.assertEqual(len(ctx.llm.calls), 3)

    async def test_comprehension_sees_only_target_in_every_request_field(self):
        ctx = Context()
        register(ctx)
        handler = ctx.tools["egm_review"]["handler"]
        target = {"id": "spec", "text": "# Design\nDeliver webhooks."}
        previous_call = None
        previous_snapshot = None
        for revision in ("SUPPORT_ONLY_FIRST", "SUPPORT_ONLY_SECOND"):
            args = {
                "target": "spec",
                "documents": [
                    {"id": f"SUPPORT_ID_{i}", "text": f"{revision}_{i}"} for i in range(7)
                ]
                + [target],
                "lenses": ["readiness", "comprehension", "design"],
            }
            result = json.loads(
                await handler(
                    args,
                    parent_agent="PRIVATE_PARENT_CANARY",
                    user_task="PRIVATE_CHAT_CANARY",
                    memory="PRIVATE_MEMORY_CANARY",
                    previous_findings="PRIVATE_REVIEW_CANARY",
                    session_id="PRIVATE_SESSION_CANARY",
                )
            )
            self.assertEqual(result["status"], "complete")
            calls = {call["purpose"].split(".")[-1]: call for call in ctx.llm.calls[-3:]}
            comprehension = calls["comprehension"]
            self.assertEqual(
                json.loads(comprehension["input"][0]["text"]),
                {
                    "target": "spec",
                    "documents": [{"id": "spec", "lines": target["text"].split("\n")}],
                },
            )
            sent = json.dumps(comprehension)
            self.assertNotIn("SUPPORT_", sent)
            self.assertNotIn(result["snapshot_id"], sent)
            for call in calls.values():
                self.assertNotIn("PRIVATE_", json.dumps(call))
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
            for lens in ("design", "readiness"):
                self.assertEqual(
                    calls[lens]["input"],
                    [{"type": "text", "text": review.ReviewRequest.parse(args).payload()}],
                )
            if previous_call is not None:
                self.assertEqual(comprehension, previous_call)
                self.assertNotEqual(result["snapshot_id"], previous_snapshot)
            previous_call = comprehension
            previous_snapshot = result["snapshot_id"]
        self.assertEqual(len(ctx.llm.calls), 6)
