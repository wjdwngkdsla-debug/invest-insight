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

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-2xl border border-white/60 bg-white/55 px-4 py-3.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-100/80 text-amber-600">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M12 9v4m0 4h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p className="text-[11.5px] font-medium text-slate-500">잔여 락업</p>
        </div>
        <p className="mt-2.5 text-[18px] font-bold leading-tight tracking-tight text-slate-900">
          {pct(remaining)}
          <span className="text-[12px] font-semibold text-slate-400">%</span>
        </p>
        <p className="mt-0.5 text-[10.5px] leading-[13px] text-slate-400">
          {remaining.toLocaleString("ko-KR")}주{nextDays !== null && ` · 다음 D-${nextDays}`}
        </p>
      </div>

      <div className="rounded-2xl border border-white/60 bg-white/55 px-4 py-3.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100/80 text-emerald-600">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4">
              <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p className="text-[11.5px] font-medium text-slate-500">해제 완료</p>
        </div>
        <p className="mt-2.5 text-[18px] font-bold leading-tight tracking-tight text-slate-900">
          {pct(released)}
          <span className="text-[12px] font-semibold text-slate-400">%</span>
        </p>
        <p className="mt-0.5 text-[10.5px] leading-[13px] text-slate-400">{released.toLocaleString("ko-KR")}주</p>
      </div>
    </div>
  );
}
