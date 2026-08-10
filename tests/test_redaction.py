from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.utils.redaction import redact_sensitive_text


class RedactionTest(unittest.TestCase):
    def test_redacts_query_string_secrets(self) -> None:
        message = (
            "https://apis.data.go.kr/example?serviceKey=very-secret-value&pageNo=1 "
            "https://opendart.fss.or.kr/api?crtfc_key=dart-secret"
        )

        redacted = redact_sensitive_text(message)

        self.assertNotIn("very-secret-value", redacted)
        self.assertNotIn("dart-secret", redacted)
        self.assertIn("serviceKey=<REDACTED>", redacted)
        self.assertIn("crtfc_key=<REDACTED>", redacted)

    def test_redacts_known_environment_values(self) -> None:
        with patch.dict(os.environ, {"KRX_API_KEY": "krx-secret-value"}, clear=False):
            redacted = redact_sensitive_text("request failed: krx-secret-value")

        self.assertEqual(redacted, "request failed: <REDACTED>")


if __name__ == "__main__":
    unittest.main()
