"""시트 수기값 → 사이트 데이터만 빠르게 갱신한다 (DART·금융위 공시 조회 없음).

콘텐츠 링크 추가, 표시 여부 변경, 수기 물량 보정처럼 **외부 공시를 새로 볼 필요가 없는**
수정을 반영할 때 쓴다. 전체 배치(scripts.build)는 DART 재파싱·금융위 반환조회·IPO일정
백필까지 모두 돌기 때문에 몇 분이 걸리지만, 이 스크립트는 네트워크를 시트(+선택적 KRX)
로만 제한해 수십 초 안에 끝난다.

사용:
    python -m scripts.quick_refresh              # 시트 수거 + site_data 재생성
    python -m scripts.quick_refresh --prices     # KRX 종가·시가총액까지 갱신
    python -m scripts.quick_refresh --no-pull    # 시트 수거 없이 로컬 CSV로만 재생성

전체 배치가 필요한 경우(이 스크립트로는 못 채우는 것):
    신규 상장 종목 편입, DART 신고서·실적보고서 파싱, 금융위 반환실적 검증, IPO일정 백필
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from scripts.build import (
    ADMIN_COLUMNS,
    REVIEW_COLUMNS,
    ROOT_DIR,
    _read_csv,
    _to_int,
    _write_csv,
    apply_manual_events,
    align_final_dates_with_api,
    discard_id_drifted_duplicates,
    finalize_row,
    load_manual_events,
    merge_review_history,
    normalize_stock_code,
    pct,
    refresh_market_data,
    rows_to_site_data,
)
from scripts.utils.redaction import redact_sensitive_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="시트 수기값만 사이트에 빠르게 반영")
    parser.add_argument("--no-pull", action="store_true", help="Google Sheet 수거를 건너뛰고 로컬 CSV만 사용")
    parser.add_argument("--prices", action="store_true", help="KRX 종가·상장주식수도 함께 갱신")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    data_dir = ROOT_DIR / "data"
    admin_path = data_dir / "lockup_admin.csv"
    out_path = data_dir / "site_data.json"

    def lap(label: str, since: float) -> None:
        print(f"[QUICK] {label} {time.perf_counter() - since:.1f}s", file=sys.stderr)

    if not args.no_pull:
        step = time.perf_counter()
        from scripts.sheets_sync import build_client, pull_admin, sheet_id

        pull_admin(build_client().open_by_key(sheet_id()))
        lap("시트 수거", step)

    step = time.perf_counter()
    rows = _read_csv(admin_path, ADMIN_COLUMNS)
    if not rows:
        raise SystemExit(f"[QUICK] {admin_path} 가 비어 있습니다 — 전체 배치를 먼저 실행하세요")

    # 시트에 새로 추가한 수기 이벤트도 빠른 갱신에서 즉시 운영 데이터로 승격한다.
    # 종목코드가 이미 운영 CSV에 있으면 그 메타데이터를 재사용하므로 별도 KRX 조회도 없다.
    manual_entries = load_manual_events()
    manual_reviews: list[dict] = []
    added_manual_entries: list[dict] = []
    if manual_entries:
        existing_by_id = {row["event_id"]: row for row in rows if row.get("event_id")}
        all_rows_by_id = dict(existing_by_id)
        existing_signatures = {
            (
                normalize_stock_code(row.get("code")),
                "기존주주" if str(row.get("category") or "") == "구주·보호예수" else str(row.get("category") or ""),
                str(row.get("period") or "").strip(),
            )
            for row in rows
        }
        added_manual_entries = [
            entry for entry in manual_entries
            if (
                normalize_stock_code(entry.get("code")),
                str(entry.get("category") or "").strip(),
                str(entry.get("period") or "").strip(),
            ) not in existing_signatures
        ]
        manual_reviews, _manual_logs = apply_manual_events(
            added_manual_entries, rows, existing_by_id, all_rows_by_id
        )
        rows = sorted(
            all_rows_by_id.values(),
            key=lambda row: (
                row.get("final_tradable_date") or row.get("planned_tradable_date") or "9999-99-99",
                row.get("code") or "",
            ),
        )

    # 수기 입력(수기물량·수기일자·잠금)을 확정값에 반영한다. 계산만 하고 외부 호출은 없다.
    # normalize_row_period는 일부러 돌리지 않는다 — 전체 배치가 기간 라벨을 손대지 않는
    # 구간(스캔 연도 밖 과거 종목)까지 여기서 바꿔버리면 두 경로의 결과가 갈린다.
    originals = [dict(row) for row in rows]  # finalize_row는 원본 dict를 제자리에서 고친다
    finalized = [finalize_row(row)[0] for row in rows]

    # 같은 예정일을 공유하는 행들을 예탁원 실제 반환일에 맞춘다. 전체 배치도 finalize
    # 뒤에 이 단계를 돌리므로, 빼면 정렬된 날짜가 원본으로 되돌아간다
    # (리센스메디컬 1개월 05-04 → 04-30처럼 화면 해제일이 밀린다).
    by_id = {r["event_id"]: r for r in finalized if r.get("event_id")}
    align_final_dates_with_api(by_id)
    # 휴장일 추가로 거래가능일이 바뀌어 ID만 갈라진 옛 행 정리 (전체 배치와 동일 단계)
    discard_id_drifted_duplicates(by_id)
    dropped = [r for r in finalized if r.get("event_id") and r["event_id"] not in by_id]
    finalized = [r for r in finalized if not (r.get("event_id") and r["event_id"] not in by_id)]
    originals = [o for o in originals if not any(o.get("event_id") == d.get("event_id") for d in dropped)]

    changed = 0
    # 비교는 CSV에 실제로 쓰이는 컬럼만 본다. finalize_row가 덧붙이는 파생 키
    # (market_cap·trading_suspended 등)는 저장되지 않으므로 변경으로 치면 안 된다.
    written = [col for col in ADMIN_COLUMNS if col != "updated_at"]
    for original, updated in zip(originals, finalized):
        # finalize_row는 편입 시점 주식수(shares)로 비율을 내지만, 전체 배치는 그 뒤
        # refresh_market_data가 현재 상장주식수(current_shares) 기준으로 덮어쓴 값을
        # 최종본으로 저장한다. 같은 기준을 쓰지 않으면 두 경로가 매번 서로 값을 되돌린다.
        current_shares = _to_int(updated.get("current_shares"))
        if current_shares:
            updated["planned_pct"] = pct(_to_int(updated.get("planned_qty")), current_shares)
            updated["final_pct"] = pct(_to_int(updated.get("final_qty")), current_shares)
        # 내용이 그대로면 갱신시각도 그대로 둔다 — 매 실행마다 1,000행이 통째로
        # 바뀐 것처럼 보이면 실제 변경을 diff에서 찾을 수 없다.
        if all(str(updated.get(col, "")) == str(original.get(col, "")) for col in written):
            updated["updated_at"] = original.get("updated_at", "")
        else:
            changed += 1
    _write_csv(admin_path, finalized, ADMIN_COLUMNS)
    lap(f"수기값 확정 {len(finalized)}행 (실제 변경 {changed}행)", step)

    # 수기 기존주주 이벤트가 하나라도 정상 편입되면 DART 표 미발견 검토는 해소된 것이다.
    # 빠른 갱신은 DART를 재조회하지 않으므로 다른 검토 건은 건드리지 않는다.
    manual_float_codes = {
        normalize_stock_code(entry.get("code"))
        for entry in added_manual_entries
        if str(entry.get("category") or "").strip() in {"기존주주", "구주·보호예수"}
        and normalize_stock_code(entry.get("code"))
        and int(str(entry.get("qty") or "0").replace(",", "") or 0) > 0
    }
    if manual_float_codes:
        review_path = data_dir / "review_needed.csv"
        current_reviews = _read_csv(review_path, REVIEW_COLUMNS)
        resolved_ids = {
            str(row.get("review_id") or "")
            for row in current_reviews
            if normalize_stock_code(row.get("code")) in manual_float_codes
            and (
                "유통가능" in str(row.get("issue") or "")
                or str(row.get("target") or "").startswith("구주·보호예수")
            )
        }
        review_history = merge_review_history(review_path, manual_reviews, resolved_ids)
        _write_csv(review_path, review_history, REVIEW_COLUMNS)

    close_date = None
    if args.prices:
        step = time.perf_counter()
        try:
            close_date, _logs = refresh_market_data(finalized)
            _write_csv(admin_path, finalized, ADMIN_COLUMNS)
        except Exception as exc:
            print(f"[QUICK] KRX 갱신 실패(기존 종가 유지): {redact_sensitive_text(exc)}", file=sys.stderr)
        lap("KRX 시세", step)

    # KRX를 돌지 않았으면 기존 site_data의 종가 기준일을 그대로 유지한다.
    # 실행일로 덮으면 오래된 가격이 오늘 가격처럼 보인다.
    previous_price_date = None
    previous_stocks: dict[str, dict] = {}
    if out_path.exists():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
            previous_price_date = previous.get("updated")
            previous_stocks = {str(s.get("code")): s for s in previous.get("stocks") or []}
        except (OSError, json.JSONDecodeError):
            previous_price_date = None

    # 거래정지 여부는 KRX 시세에서만 나오고 CSV에는 저장되지 않는다. 시세를 갱신하지
    # 않는 실행에서는 직전 site_data의 판정을 그대로 이어받아야 정지 종목이 풀리지 않는다.
    if not close_date and previous_stocks:
        for row in finalized:
            stock = previous_stocks.get(str(row.get("code") or ""))
            if stock:
                row["trading_suspended"] = stock.get("trading_suspended") is True
                row["trading_suspended_since"] = str(stock.get("trading_suspended_since") or "")

    step = time.perf_counter()
    site_data = rows_to_site_data(finalized, close_date or previous_price_date)
    # 빠른 갱신은 외부 시세를 새로 받지 않으므로 기존 사이트의 API 사유 세부내역과
    # 해제일 종가/등락률처럼 CSV 밖에만 남는 파생값을 그대로 보존한다.
    if previous_stocks:
        for stock in site_data.get("stocks") or []:
            previous_stock = previous_stocks.get(str(stock.get("code") or ""))
            if not previous_stock:
                continue
            previous_events = {
                (
                    str(event.get("category") or ""),
                    str(event.get("period") or ""),
                    str(event.get("tradable_date") or ""),
                    int(event.get("qty") or 0),
                ): event
                for event in previous_stock.get("events") or []
            }
            for event in stock.get("events") or []:
                old = previous_events.get((
                    str(event.get("category") or ""),
                    str(event.get("period") or ""),
                    str(event.get("tradable_date") or ""),
                    int(event.get("qty") or 0),
                ))
                if not old:
                    continue
                for field in ("reason_breakdown", "release_close", "release_fluc_rt"):
                    if field in old:
                        event[field] = old[field]
    out_path.write_text(json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8")
    lap(f"site_data 재생성 {len(site_data.get('stocks') or [])}종목", step)

    print(f"[QUICK] 완료 — 총 {time.perf_counter() - started:.1f}s / {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
