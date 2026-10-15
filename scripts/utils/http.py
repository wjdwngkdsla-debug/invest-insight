"""외부 API 호출에 공통으로 붙이는 재시도 규칙.

배치가 실패하거나 데이터가 조용히 비는 사고는 대부분 한 번의 일시적 응답 때문이었다.
  - Google Sheets 503 → 배치 전체 실패 (run 36950005265)
  - apis.data.go.kr read timeout → 해당 종목만 건너뛰고 계속 (run 37870912742, 4종목)
  - KRX 한쪽 시장만 빈 응답 → 그 시장 종목이 통째로 사라진 채 정상 처리
한 번 더 물어보면 끝날 일이라 호출부마다 같은 규칙을 쓴다.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 지수 백오프: 1s → 2s → 4s → 8s. 총 대기 15초로 일시적 장애는 넘기고,
# 진짜 장애일 때는 배치를 오래 붙잡지 않는다.
DEFAULT_RETRY_TOTAL = 4
DEFAULT_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)


def build_retry(total: int = DEFAULT_RETRY_TOTAL, backoff: float = DEFAULT_BACKOFF) -> Retry:
    return Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=RETRY_STATUS,
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )


def mount_retries(
    session: requests.Session,
    total: int = DEFAULT_RETRY_TOTAL,
    backoff: float = DEFAULT_BACKOFF,
) -> requests.Session:
    """이미 만들어진 세션에 재시도를 붙인다(gspread의 AuthorizedSession 등)."""
    adapter = HTTPAdapter(max_retries=build_retry(total, backoff))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def retry_session(
    total: int = DEFAULT_RETRY_TOTAL,
    backoff: float = DEFAULT_BACKOFF,
) -> requests.Session:
    return mount_retries(requests.Session(), total, backoff)
