from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    """간단한 .env 로더. python-dotenv 의존성을 줄이기 위해 직접 구현."""
    env_path = path or ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()

KRX_API_KEY = os.getenv("KRX_API_KEY")
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY", "")

PUBLIC_LOCKUP_API_URL = (
    "https://apis.data.go.kr/1160100/"
    "GetStocIssuInfoService_V3/getLockUpRetuInfo_V3"
)

KRX_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "AUTH_KEY": KRX_API_KEY or "",
}

KRX_URLS = [
    ("https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd", "코스피"),
    ("https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd", "코스닥"),
]

USER_AGENT = {"User-Agent": "Mozilla/5.0"}


def require_env() -> None:
    missing: list[str] = []
    if not KRX_API_KEY:
        missing.append("KRX_API_KEY")
    if not DATA_GO_KR_API_KEY:
        missing.append("DATA_GO_KR_API_KEY")
    if not DART_API_KEY:
        missing.append("DART_API_KEY")
    if missing:
        raise RuntimeError("필수 환경변수가 없습니다: " + ", ".join(missing))
