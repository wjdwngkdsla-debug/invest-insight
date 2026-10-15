"""외부 API 호출에 공통으로 붙이는 재시도 규칙.

배치가 실패하거나 데이터가 조용히 비는 사고는 대부분 한 번의 일시적 응답 때문이었다.
  - Google Sheets 503 → 배치 전체 실패 (run 36950005265)
  - apis.data.go.kr read timeout → 해당 종목만 건너뛰고 계속 (run 37870912742, 4종목)
  - KRX 한쪽 시장만 빈 응답 → 그 시장 종목이 통째로 사라진 채 정상 처리
한 번 더 물어보면 끝날 일이라 호출부마다 같은 규칙을 쓴다.
"""

from __future__ import annotations

import sys

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 재시도는 "가끔 한 번 실패"에 듣는 약이지 "계속 죽어 있음"에는 독이다.
# run 38754667197에서 apis.data.go.kr가 49분간 완전히 죽자, 재시도 4회가
# 종목당 30초를 2.8분으로 늘려 17종목을 날리고 배치가 90분 상한에 걸렸다.
# 그래서 재시도는 짧게 잡고, 지속 장애는 아래 CircuitBreaker가 끊는다.
DEFAULT_RETRY_TOTAL = 2
DEFAULT_BACKOFF = 0.5
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


class CircuitBreaker:
    """연속 실패가 쌓이면 그 API를 이번 실행에서 포기한다.

    재시도만 있으면 장애가 길어질수록 배치가 기하급수로 느려진다. 어차피 다음
    종목도 같은 이유로 실패할 거라면, 기다리지 말고 즉시 건너뛰고 끝까지 돌아
    나머지 데이터라도 남기는 편이 낫다. 한 번이라도 성공하면 계수를 되돌린다.
    """

    def __init__(self, name: str, threshold: int = 5) -> None:
        self.name = name
        self.threshold = threshold
        self.consecutive_failures = 0
        self.tripped = False
        self.skipped = 0

    def allow(self) -> bool:
        if self.tripped:
            self.skipped += 1
        return not self.tripped

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and not self.tripped:
            self.tripped = True
            print(
                f"[{self.name}] 연속 {self.threshold}회 실패 — 이번 실행에서는 더 호출하지 "
                f"않고 건너뜁니다. 해당 데이터는 다음 배치에서 다시 시도합니다.",
                file=sys.stderr,
            )

    def summary(self) -> str:
        if not self.tripped:
            return ""
        return f"[{self.name}] 장애로 {self.skipped}종목을 건너뛰었습니다 (이번 실행 한정)."
