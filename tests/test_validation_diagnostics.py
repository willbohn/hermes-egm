"""Synthetic offline replies: diagnostics, not reconstructed provider output."""

import json
import unittest
from copy import deepcopy
from dataclasses import replace

from test_findings import finding, request
from test_runner import FakeLlm, Reply

from hermes_egm import review


class ValidationDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_schema_rejections_do_not_echo_untrusted_values(self):
        item = finding()
        cases = [
            [],
            "REJECTED_RESPONSE_CANARY",
            {1: []},
            {},
            {"findings": None},
            {"findings": [None]},
            {"findings": [item] * 9},
        ]
        for changes in (
            {"severity": "REJECTED_RESPONSE_CANARY"},
            {"title": " "},
            {"title": "x" * 161},
            {"detail": "x" * 1001},
            {"suggestion": "x" * 601},
            {"detail": 42},
            {"evidence": None},
            {"evidence": []},
            {"evidence": [{}]},
            {"evidence": [None]},
            {"evidence": item["evidence"] * 4},
            {"extra": "REJECTED_RESPONSE_CANARY"},
        ):
            cases.append({"findings": [{**item, **changes}]})
        for parsed in cases:
            with self.subTest(parsed=parsed), self.assertRaises(review.InvalidReview) as raised:
                review.validate_findings(parsed, request(), "design")
            self.assertEqual(raised.exception.code, "schema_invalid")
            self.assertNotIn("REJECTED_RESPONSE_CANARY", str(raised.exception))

    def test_one_based_citations_match_literal_payload_lines(self):
        text = '# Heading\r\n\nCafé: "quoted" \\ path\n```mermaid\n  preserve  spaces\n'
        req = review.ReviewRequest.parse(
            {"target": "spec", "documents": [{"id": "spec", "text": text}]}
        )
        lines = json.loads(req.payload())["documents"][0]["lines"]
        self.assertEqual(lines, text.split("\n"))
        for index, line in enumerate(lines, 1):
            if not line.strip():
                continue
            item = finding()
            item["evidence"][0].update(line=index, quote=line)
            raw = {"findings": [item]}
            before = deepcopy(raw)
            accepted = review.validate_findings(raw, req, "design")
            self.assertEqual(accepted[0]["evidence"], item["evidence"])
            self.assertEqual(raw, before)
        for quote in ('Café: "quoted" \\ path\n```mermaid', "café", "Café: “quoted”", "Cafe\u0301"):
            item = finding()
            item["evidence"][0].update(line=3, quote=quote)
            with self.subTest(quote=quote), self.assertRaises(review.InvalidReview) as raised:
                review.validate_findings({"findings": [item]}, req, "design")
            self.assertEqual(raised.exception.code, "quote_mismatch")

    def test_citation_locations_have_distinct_codes(self):
        cases = [
            ({"document": "UNKNOWN_SOURCE_CANARY"}, "unknown_document"),
            ({"line": 0}, "line_out_of_range"),
            ({"line": 3}, "line_out_of_range"),
            ({"line": True}, "schema_invalid"),
            ({"line": 2.0}, "schema_invalid"),
            ({"line": "2"}, "schema_invalid"),
            ({"quote": " "}, "schema_invalid"),
            ({"quote": "x" * 401}, "schema_invalid"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                item = finding()
                item["evidence"][0].update(changes)
                with self.assertRaises(review.InvalidReview) as raised:
                    review.validate_findings({"findings": [item]}, request(), "design")
                self.assertEqual(raised.exception.code, expected)
                self.assertNotIn("UNKNOWN_SOURCE_CANARY", str(raised.exception))

    async def test_validation_stages_have_safe_codes_without_accepting_partial_findings(self):
        wrong_quote = finding()
        wrong_quote["evidence"][0]["quote"] = "REJECTED_RESPONSE_CANARY"
        cases = [
            (None, "parsed_unavailable"),
            ({"findings": [], "REJECTED_RESPONSE_CANARY": True}, "schema_invalid"),
            ({"findings": [finding(), wrong_quote]}, "quote_mismatch"),
        ]
        for parsed, expected in cases:
            with self.subTest(code=expected):

                class FixtureLlm(FakeLlm):
                    def __init__(self, response):
                        super().__init__()
                        self.response = response

                    async def acomplete_structured(self, **kwargs):
                        self.calls.append(kwargs)
                        return Reply(
                            parsed=self.response
                            if kwargs["purpose"].endswith("design")
                            else {"findings": []}
                        )

                llm = FixtureLlm(parsed)
                result = await review.run_review(
                    llm, replace(request(), lenses=("design", "readiness"))
                )
                design, readiness = result["reviewers"]
                self.assertEqual(design.get("validation_error"), expected)
                self.assertEqual(design["status"], "failed")
                self.assertEqual(
                    design["error"],
                    "invalid_response: reviewer output failed local validation; "
                    "no findings accepted.",
                )
                self.assertEqual(design["findings"], [])
                self.assertEqual(design["provider"], "test-provider")
                self.assertEqual(design["usage"]["total_tokens"], 30)
                self.assertEqual(readiness["status"], "complete")
                self.assertIn("validation_error", readiness)
                self.assertIsNone(readiness.get("validation_error"))
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["outcome"], "incomplete")
                self.assertEqual(result["findings"], [])
                self.assertEqual(len(llm.calls), 2)
                self.assertNotIn("REJECTED_RESPONSE_CANARY", json.dumps(result))

    async def test_missing_parsed_value_does_not_inspect_or_repair_raw_text(self):
        class UnparsedReply(Reply):
            @property
            def text(self):
                raise AssertionError("RAW_REPLY_MUST_NOT_BE_READ")

        class UnparsedLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return UnparsedReply(parsed=None)

        llm = UnparsedLlm()
        result = await review.run_review(llm, replace(request(), lenses=("design",)))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertEqual(result["reviewers"][0]["validation_error"], "parsed_unavailable")
        self.assertEqual(len(llm.calls), 1)

    async def test_host_exceptions_are_not_labeled_as_local_validation_errors(self):
        for error, category in (
            (ValueError("HOST_EXCEPTION_CANARY"), "provider_error"),
            (review.InvalidReview("HOST_EXCEPTION_CANARY"), "provider_error"),
            (TimeoutError("HOST_EXCEPTION_CANARY"), "timeout"),
        ):
            with self.subTest(category=category, exception=type(error).__name__):

                class FailingLlm(FakeLlm):
                    def __init__(self, exception):
                        super().__init__()
                        self.exception = exception

                    async def acomplete_structured(self, **kwargs):
                        self.calls.append(kwargs)
                        raise self.exception

                llm = FailingLlm(error)
                result = await review.run_review(llm, replace(request(), lenses=("design",)))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["outcome"], "incomplete")
                self.assertTrue(result["reviewers"][0]["error"].startswith(category + ":"))
                self.assertIsNone(result["reviewers"][0]["validation_error"])
                self.assertNotIn("HOST_EXCEPTION_CANARY", json.dumps(result))
                self.assertEqual(len(llm.calls), 1)

    async def test_public_handler_serializes_the_diagnostic_and_preserves_manual_intent(self):
        from test_plugin import Context

        from hermes_egm.plugin import register

        class InvalidLlm(FakeLlm):
            async def acomplete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return Reply(parsed=None)

        ctx = Context()
        ctx.llm = InvalidLlm()
        register(ctx)
        result = json.loads(
            await ctx.tools["egm_review"]["handler"](
                {
                    "automatic": False,
                    "target": "spec",
                    "documents": [{"id": "spec", "text": "Synthetic design."}],
                    "lenses": ["design"],
                }
            )
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertIs(result["automatic"], False)
        self.assertEqual(result["reviewers"][0]["validation_error"], "parsed_unavailable")
        self.assertEqual(len(ctx.llm.calls), 1)
