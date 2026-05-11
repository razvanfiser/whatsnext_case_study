"""Tests for annotator_backend.pii_redact."""

from __future__ import annotations

import unittest

from annotator_backend.pii_redact import (
    REDACTED_API_KEY,
    REDACTED_CREDIT_CARD,
    REDACTED_PHONE,
    REDACTED_SSN,
    redact_for_llm,
)


class RedactForLlmTests(unittest.TestCase):
    def test_ssn_replaced_and_email_preserved(self) -> None:
        raw = "Reach me at jane.doe@example.com my SSN is 123-45-6789 thanks"
        out = redact_for_llm(raw)
        self.assertIn("jane.doe@example.com", out)
        self.assertIn(REDACTED_SSN, out)
        self.assertNotIn("123-45-6789", out)

    def test_us_phone_replaced(self) -> None:
        raw = "Callback (415) 555-0199"
        out = redact_for_llm(raw)
        self.assertIn(REDACTED_PHONE, out)
        self.assertNotIn("415", out)
        self.assertNotIn("0199", out)

    def test_sk_key_replaced(self) -> None:
        raw = "key sk-abcdefghijklmnopqrstuvwxyz0123456789AB extra"
        out = redact_for_llm(raw)
        self.assertIn(REDACTED_API_KEY, out)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz0123456789AB", out)

    def test_bearer_replaced(self) -> None:
        raw = "I pasted Authorization: Bearer superlongtokenvaluehere1234567890 by mistake"
        out = redact_for_llm(raw)
        self.assertIn(REDACTED_API_KEY, out)
        self.assertNotIn("superlongtokenvaluehere1234567890", out)

    def test_card_like_replaced(self) -> None:
        raw = "Card 4111 1111 1111 1111 expired"
        out = redact_for_llm(raw)
        self.assertIn(REDACTED_CREDIT_CARD, out)
        self.assertNotIn("4111", out)

    def test_empty_string(self) -> None:
        self.assertEqual(redact_for_llm(""), "")

    def test_cc_pattern_may_match_long_numeric_ids(self) -> None:
        # Documented limitation: 13+ digit runs can false-positive as card-like (orders,
        # invoice numbers). Safer to accept that for this lightweight layer.
        raw = "order id 12345678901234"
        out = redact_for_llm(raw)
        self.assertIn(REDACTED_CREDIT_CARD, out)


if __name__ == "__main__":
    unittest.main()
