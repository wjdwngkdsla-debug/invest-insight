"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { UpcomingGroup } from "@/lib/data";

function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}

const PERIOD_PRIORITY = ["15일", "1개월", "2개월", "3개월", "6개월", "12개월", "1년", "24개월", "2년", "30개월", "36개월", "3년"];

function groupTitle(periods: string[]): string {
  const period = PERIOD_PRIORITY.find((p) => periods.includes(p));
  if (period) return `${period} 락업 해제`;
  if (periods.length === 1) return `${periods[0]} 락업 해제`;
  return "락업 해제";
}

function dDayOf(dateStr: string): number {
  const target = new Date(dateStr);
  const now = new Date();
  const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - t0.getTime()) / (1000 * 60 * 60 * 24));
}

function Popup({ ev }: { ev: UpcomingGroup }) {
  return (
    <Link
      href={`/stock/${ev.stockCode}`}
      className="card block w-[320px] rounded-2xl p-5 shadow-[0_4px_8px_rgba(23,21,15,0.06),0_24px_56px_-16px_rgba(23,21,15,0.25)]"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[15px] font-bold">{ev.stockName}</p>
        <div className="shrink-0 text-right">
          <p className="text-[15px] font-bold tabular-nums">{formatQty(ev.qty)}주</p>
          <p className="text-xs text-ink-muted tabular-nums">({ev.pct}%)</p>
        </div>
      </div>

      <p className="mt-3 text-sm text-ink-soft tabular-nums">
        {ev.tradable_date} · {groupTitle(ev.periods)}
      </p>
      <p className="mt-0.5 text-sm text-ink-muted tabular-nums">
        {ev.market} · 상장일 {ev.listing_date}
      </p>

      {ev.breakdown.length > 0 && (
        <div className="mt-3 space-y-1 border-t border-hairline pt-3 text-sm">
          {ev.breakdown.map((b) => (
            <div key={b.category} className="flex items-baseline justify-between gap-3">
              <span className="text-ink-muted">{b.category}</span>
              <span className="font-medium text-ink-soft tabular-nums">
                {formatQty(b.qty)}주 ({b.pct}%)
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="mt-4 text-xs font-medium text-ink-muted">클릭하면 종목 상세 페이지로 이동 →</p>
    </Link>
  );
}

export function UpcomingList({ events }: { events: UpcomingGroup[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function show(i: number) {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    setOpenIndex(i);
  }

  // 카드에서 팝업으로 마우스를 옮기는 동안 잠깐 비는 구간이 있어도 팝업이 유지되도록 지연 후 닫는다
  function scheduleHide() {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setOpenIndex(null), 180);
  }

  if (events.length === 0) {
    return <p className="card rounded-2xl p-6 text-center text-sm text-ink-muted">30일 이내 예정된 해제 이벤트가 없습니다.</p>;
  }

  return (
    <ul className="flex gap-3 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
      {events.map((ev, i) => {
        const d = dDayOf(ev.tradable_date);
        const isHighPct = ev.pct >= 5;
        return (
          <li
            key={`${ev.stockCode}-${ev.tradable_date}-${i}`}
            className="relative min-w-[190px] shrink-0 lg:min-w-0"
            onMouseEnter={() => show(i)}
            onMouseLeave={scheduleHide}
          >
            <Link
              href={`/stock/${ev.stockCode}`}
              className="card block rounded-2xl px-4 py-4 transition-shadow hover:shadow-[0_2px_4px_rgba(23,21,15,0.04),0_16px_40px_-18px_rgba(23,21,15,0.18)]"
            >
              <span
                className={`inline-block rounded-full px-2.5 py-1 text-xs font-bold tabular-nums ${
                  d <= 3 ? "bg-[#ffe5e5] text-alert" : "bg-sky text-sky-ink"
                }`}
              >
                D-{d}
              </span>
              <p className="mt-2.5 text-[15px] font-semibold">{ev.stockName}</p>
              <p className={`mt-1 text-sm tabular-nums ${isHighPct ? "font-semibold text-alert" : "text-ink-soft"}`}>
                {formatQty(ev.qty)}주 ({ev.pct}%)
              </p>
            </Link>

            {openIndex === i && (
              <div
                className="absolute left-full top-0 z-50 ml-3 hidden lg:block"
                onMouseEnter={() => show(i)}
                onMouseLeave={scheduleHide}
              >
                <Popup ev={ev} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
