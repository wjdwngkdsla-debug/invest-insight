from __future__ import annotations

import os
import re


_QUERY_SECRET_RE = re.compile(
    r"(?i)(serviceKey|crtfc_key|auth_key|api_key|client_secret|client_id)"
    r"(=|%3D)([^&\s,\"']+)"
)
_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,\"']+")


def redact_sensitive_text(value: object) -> str:
    """로그·검토사유에 들어가기 전 인증정보를 제거한다."""
    text = str(value)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<REDACTED>", text)
    text = _BEARER_RE.sub(r"\1<REDACTED>", text)

    for env_name in (
        "KRX_API_KEY",
        "DATA_GO_KR_API_KEY",
        "DART_API_KEY",
        "TOSS_CLIENT_ID",
        "TOSS_CLIENT_SECRET",
    ):
        secret = os.getenv(env_name, "").strip()
        if secret:
            text = text.replace(secret, "<REDACTED>")

    return text
