"""KRX 일별 시세만으로 권리락 조정계수를 계산한다 (토스 대체).

거래소 등락률은 기준가 대비다. 따라서
    기준가 = 종가 ÷ (1 + 등락률/100)
이고, 이 기준가가 전 거래일 종가와 다른 날이 권리락일이며 두 값의 비가 그 날의
조정계수다. 여러 번이면 곱한다.

지투지바이오 2025-11-05에서 185,000 → 기준가 61,700, 계수 0.3335가 나오고
토스 수정주가로 역산한 0.3334968과 일치하는 것을 확인했다.

토스와 달리 허용 IP 등록이 필요 없어 GitHub Actions에서 그대로 돌릴 수 있다.

사용:
    python -m scripts.price_adjustments            # 캐시에 없는 날짜만 이어서
    python -m scripts.price_adjustments --rebuild  # 처음부터 다시
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.sources.krx import krx_snapshot

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT_DIR / "data" / "price_adjustments.json"
SITE_DATA_PATH = ROOT_DIR / "data" / "site_data.json"

# 종가가 기준가와 이만큼 어긋나면 권리락으로 본다. 호가단위 반올림 때문에
# 조정이 없는 날도 0.01% 안팎으로 흔들려서 여유를 둔다.
EVENT_THRESHOLD = 0.02


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_date": "", "stocks": {}}


def _targets() -> dict[str, str]:
    """{종목코드: 상장일}"""
    data = json.loads(SITE_DATA_PATH.read_text(encoding="utf-8"))
    return {
        stock["code"]: stock.get("listing_date") or ""
        for stock in data.get("stocks", [])
        if stock.get("code")
    }


def scan(rebuild: bool = False) -> dict:
    state = {"last_date": "", "stocks": {}} if rebuild else _load_state()
    stocks: dict[str, dict] = state.setdefault("stocks", {})
    targets = _targets()
    if not targets:
        raise SystemExit("site_data.json에 종목이 없습니다")

    start_iso = state.get("last_date") or min(d for d in targets.values() if d)
    start = datetime.strptime(start_iso, "%Y-%m-%d").date() + (
        timedelta(days=1) if state.get("last_date") else timedelta(0)
    )
    today = date.today()
    if start > today:
        print("[조정계수] 새로 볼 거래일 없음", file=sys.stderr)
        return state

    print(f"[조정계수] {start} ~ {today} 스캔 (종목 {len(targets)})", file=sys.stderr)
    scanned = events = 0
    day = start
    while day <= today:
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        try:
            snapshot = krx_snapshot(day.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"  [KRX] {day} 조회 실패(건너뜀): {type(exc).__name__}", file=sys.stderr)
            snapshot = None
        if not snapshot:
            day += timedelta(days=1)
            continue
        scanned += 1
        for code, listing in targets.items():
            if listing and day.isoformat() < listing:
                continue
            meta = snapshot.get(code)
            if not meta or not meta.get("close_price"):
                continue
            entry = stocks.setdefault(code, {"factor": 1.0, "events": [], "prev_close": 0})
            close = meta["close_price"]
            prev_close = entry.get("prev_close") or 0
            fluc = meta.get("fluc_rt")
            if prev_close and fluc is not None:
                base = close / (1 + fluc / 100)
                gap = abs(base - prev_close) / prev_close
                if gap > EVENT_THRESHOLD:
                    factor = base / prev_close
                    entry["events"].append({
                        "date": day.isoformat(),
                        "factor": round(factor, 7),
                        "prev_close": prev_close,
                        "base_price": round(base),
                    })
                    entry["factor"] = round(entry["factor"] * factor, 7)
                    events += 1
                    print(
                        f"  [권리락] {day} {code} {prev_close:,} → 기준가 {base:,.0f} "
                        f"(계수 {factor:.4f})",
                        file=sys.stderr,
                    )
            entry["prev_close"] = close
        state["last_date"] = day.isoformat()
        day += timedelta(days=1)

    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    adjusted = sum(1 for v in stocks.values() if abs(v.get("factor", 1) - 1) > 0.0001)
    print(
        f"[조정계수] 거래일 {scanned}일 스캔 / 권리락 {events}건 / 조정 종목 {adjusted}개",
        file=sys.stderr,
    )
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="KRX 시세로 권리락 조정계수 계산")
    parser.add_argument("--rebuild", action="store_true", help="캐시를 버리고 처음부터 다시")
    scan(rebuild=parser.parse_args().rebuild)


if __name__ == "__main__":
    main()
