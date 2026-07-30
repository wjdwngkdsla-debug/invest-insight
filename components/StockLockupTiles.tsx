"use client";

import { useEffect, useState } from "react";
import type { LockupEvent } from "@/lib/types";

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 86_400_000;

function kstDayNumber(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS);
}

/** 잔여 오버행·해제 완료는 "오늘"에 따라 바뀐다. 정적 배포본이 하루 지나도 틀리지 않게
 *  서버 렌더 값 대신 마운트 후 클라이언트 시각으로 계산한다(하이드레이션 불일치 방지). */
export function StockLockupTiles({
  events,
  shares,
  initialNow,
}: {
  events: LockupEvent[];
  shares: number;
  initialNow: number;
}) {
  const [nowMs, setNowMs] = useState(initialNow);
  useEffect(() => {
    const timer = window.setTimeout(() => setNowMs(Date.now()), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const today = kstDayNumber(nowMs);
  let remaining = 0;
  let released = 0;
  let nextDays: number | null = null;
  for (const event of events) {
    const day = kstDayNumber(Date.parse(`${event.tradable_date}T00:00:00+09:00`));
    if (day >= today) {
      remaining += event.qty;
      const gap = day - today;
      if (nextDays === null || gap < nextDays) nextDays = gap;
    } else {
      released += event.qty;
    }
  }
  const pct = (qty: number) => (shares > 0 ? ((qty / shares) * 100).toFixed(1) : "0.0");

  const remainPct = shares > 0 ? (remaining / shares) * 100 : 0;
  const releasedPct = shares > 0 ? (released / shares) * 100 : 0;

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl md:rounded-2xl md:px-4 md:py-3.5">
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex min-w-0 items-center gap-1.5 md:gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-amber-100/80 text-amber-600 md:h-7 md:w-7 md:rounded-lg">
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M12 9v4m0 4h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <p className="truncate text-[10.5px] font-medium text-slate-500 md:text-[11.5px]">잔여 락업</p>
          </div>
          {nextDays !== null && (
            <span className="shrink-0 whitespace-nowrap rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
              D-{nextDays}
            </span>
          )}
        </div>
        <p className="mt-1.5 text-[15px] font-bold leading-tight tracking-tight text-slate-900 md:mt-2.5 md:text-[18px]">
          {pct(remaining)}
          <span className="text-[11px] font-semibold text-slate-400 md:text-[12px]">%</span>
        </p>
        <p className="mt-0.5 text-[9.5px] leading-[12px] text-slate-400 md:text-[10.5px] md:leading-[13px]">
          {remaining.toLocaleString("ko-KR")}주
        </p>
        <span className="mt-2 hidden h-1 w-full overflow-hidden rounded-full bg-slate-900/10 md:block">
          <span className="block h-full rounded-full bg-amber-400" style={{ width: `${Math.min(100, remainPct)}%` }} />
        </span>
      </div>

      <div className="rounded-xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl md:rounded-2xl md:px-4 md:py-3.5">
        <div className="flex items-center gap-1.5 md:gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-100/80 text-emerald-600 md:h-7 md:w-7 md:rounded-lg">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4">
              <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p className="truncate text-[10.5px] font-medium text-slate-500 md:text-[11.5px]">해제 완료</p>
        </div>
        <p className="mt-1.5 text-[15px] font-bold leading-tight tracking-tight text-slate-900 md:mt-2.5 md:text-[18px]">
          {pct(released)}
          <span className="text-[11px] font-semibold text-slate-400 md:text-[12px]">%</span>
        </p>
        <p className="mt-0.5 text-[9.5px] leading-[12px] text-slate-400 md:text-[10.5px] md:leading-[13px]">
          {released.toLocaleString("ko-KR")}주
        </p>
        <span className="mt-2 hidden h-1 w-full overflow-hidden rounded-full bg-slate-900/10 md:block">
          <span className="block h-full rounded-full bg-emerald-400" style={{ width: `${Math.min(100, releasedPct)}%` }} />
        </span>
      </div>
    </div>
  );
}
