from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from scripts.config import ROOT_DIR
from scripts.sources.krx import krx_snapshot
from scripts.sources.dart import parse_ipo_lockup


@dataclass
class UniverseResult:
    confirmed: list[dict]
    review: list[dict]
    excluded: list[dict]


def _date_range(start: datetime, end: datetime) -> Iterable[datetime]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def cached_krx_snapshot(bas_dd: str) -> dict[str, dict] | None:
    """KRX 일별 스냅샷 캐시. 재실행 시 API 호출량과 시간을 줄인다."""
    cache_dir = ROOT_DIR / "data" / "cache" / "krx"
    _ensure_dir(cache_dir)
    cache_path = cache_dir / f"{bas_dd}.json"

    if cache_path.exists():
        saved = json.loads(cache_path.read_text(encoding="utf-8"))
        if saved.get("empty"):
            return None
        return saved.get("data") or {}

    snap = krx_snapshot(bas_dd)
    payload = {"empty": snap is None, "data": snap or {}}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return snap


def previous_trading_snapshot(start: datetime, lookback_days: int = 20) -> tuple[str | None, dict[str, dict] | None]:
    for back in range(1, lookback_days + 1):
        d = (start - timedelta(days=back)).strftime("%Y%m%d")
        snap = cached_krx_snapshot(d)
        if snap:
            return d, snap
    return None, None


def is_common_stock_code(code: str) -> bool:
    # 주의: isdigit() 금지. 0001A0 같은 영문혼용 보통주 코드가 존재한다.
    return len(code) == 6 and code[-1] == "0"


def is_preferred_stock_name(name: str) -> bool:
    # 단순히 '우' 포함으로 제외하면 정상 회사명까지 빠질 수 있어 끝자리/전형 패턴 중심으로 본다.
    return bool(
        name.endswith("우")
        or re.search(r"\d우B?$", name)
        or re.search(r"[1-9]우\(?전환\)?", name)
        or "우선주" in name
    )


def first_pass_exclusion_reason(code: str, name: str) -> str | None:
    upper = name.upper()

    if not is_common_stock_code(code):
        return "보통주 코드 아님"
    if "스팩" in name or "기업인수목적" in name or "SPAC" in upper:
        return "스팩"
    if "리츠" in name or "REIT" in upper:
        return "리츠"
    if "ETF" in upper or "ETN" in upper:
        return "ETF/ETN"
    if is_preferred_stock_name(name):
        return "우선주"
    return None


def discover_listing_candidates(year: int, end_date: str | None = None) -> list[dict]:
    """
    KRX 일별 스냅샷 차이로 신규상장 후보를 수집한다.
    이 단계는 IPO 확정이 아니라 '상장종목 신규 등장 후보' 수집이다.
    """
    start = datetime(year, 1, 1)
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.today()
    if end.year > year:
        end = datetime(year, 12, 31)

    prev_date, prev_snap = previous_trading_snapshot(start)
    prev_snap = prev_snap or {}
    candidates: list[dict] = []
    seen_codes: set[str] = set(prev_snap.keys())

    if prev_date:
        print(f"[UNIVERSE] previous trading snapshot: {prev_date}", file=sys.stderr)
    print(f"[UNIVERSE] scanning KRX snapshots: {start:%Y-%m-%d} ~ {end:%Y-%m-%d}", file=sys.stderr)

    for d in _date_range(start, end):
        bas_dd = d.strftime("%Y%m%d")
        snap = cached_krx_snapshot(bas_dd)
        if not snap:
            continue

        new_codes = [code for code in snap.keys() if code not in seen_codes]
        for code in new_codes:
            meta = snap[code]
            name = meta.get("name", "")
            candidates.append({
                "name": name,
                "code": code,
                "market": meta.get("market"),
                "listing_date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}",
                "shares": meta.get("shrs", 0),
                "close_price": meta.get("close_price", 0),
                "detected_bas_dd": bas_dd,
            })

        seen_codes = set(snap.keys())
        time.sleep(0.03)

    print(f"[UNIVERSE] KRX 신규상장 후보 {len(candidates)}건", file=sys.stderr)
    return candidates


def classify_candidate(candidate: dict) -> tuple[str, str, dict]:
    """반환: status(IPO확정/제외/수동확인), reason, extra."""
    name = candidate["name"]
    code = candidate["code"]

    excluded = first_pass_exclusion_reason(code, name)
    if excluded:
        return "제외", excluded, {}

    rcp, parsed, note = parse_ipo_lockup(name)
    extra = {"rcp": rcp, "parsed_ipo_lockups": parsed}

    if parsed:
        return "IPO확정", "DART 증권발행실적보고서 수요예측/의무보유확약 표 확인", extra

    # 증권발행실적보고서가 없거나 표가 안 잡히는 경우는 자동 반영하지 않고 리뷰로 보낸다.
    if note and "비공모" in note:
        return "수동확인", note, extra
    if not rcp:
        return "수동확인", "DART 증권발행실적보고서 미발견", extra
    return "수동확인", note or "IPO 여부 불확실", extra


def build_ipo_universe(year: int, end_date: str | None = None) -> UniverseResult:
    candidates = discover_listing_candidates(year, end_date=end_date)
    confirmed: list[dict] = []
    review: list[dict] = []
    excluded: list[dict] = []

    for idx, cand in enumerate(candidates, start=1):
        name = cand["name"]
        print(f"[CLASSIFY] {idx}/{len(candidates)} {name}", file=sys.stderr)
        status, reason, extra = classify_candidate(cand)
        row = {**cand, **extra, "classification": status, "classification_reason": reason}
        if status == "IPO확정":
            confirmed.append(row)
            print(f"  [IPO] {reason}", file=sys.stderr)
        elif status == "제외":
            excluded.append(row)
            print(f"  [EXCLUDE] {reason}", file=sys.stderr)
        else:
            review.append(row)
            print(f"  [REVIEW] {reason}", file=sys.stderr)
        time.sleep(0.1)

    return UniverseResult(confirmed=confirmed, review=review, excluded=excluded)


def write_universe_files(result: UniverseResult, year: int) -> None:
    data_dir = ROOT_DIR / "data"
    _ensure_dir(data_dir)
    (data_dir / f"ipo_universe_{year}.json").write_text(
        json.dumps(result.confirmed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / f"review_candidates_{year}.json").write_text(
        json.dumps(result.review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / f"excluded_listings_{year}.json").write_text(
        json.dumps(result.excluded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[UNIVERSE] saved confirmed={len(result.confirmed)} review={len(result.review)} excluded={len(result.excluded)}",
        file=sys.stderr,
    )


def load_or_build_ipo_universe(year: int, refresh: bool = True, end_date: str | None = None) -> list[dict]:
    """
    기본값은 refresh=True.
    서비스 목적상 2026 신규상장 전체를 기준으로 매번 최신 후보를 확인한다.
    API 호출 시간을 줄이고 싶으면 build.py --no-refresh-universe 를 사용한다.
    """
    universe_path = ROOT_DIR / "data" / f"ipo_universe_{year}.json"
    if universe_path.exists() and not refresh:
        return json.loads(universe_path.read_text(encoding="utf-8"))

    result = build_ipo_universe(year, end_date=end_date)
    write_universe_files(result, year)
    return result.confirmed
