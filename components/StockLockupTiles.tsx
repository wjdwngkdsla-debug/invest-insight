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

  const trackedLockup = remaining + released;
  const remainingShare = trackedLockup > 0 ? (remaining / trackedLockup) * 100 : 0;
  const releasedShare = trackedLockup > 0 ? (released / trackedLockup) * 100 : 0;

  return (
    <div className="rounded-xl border border-white/60 bg-white/55 px-3.5 py-2.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl md:px-4 md:py-2.5">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            <p className="text-[11.5px] font-semibold text-slate-600">잔여 락업</p>
            <div className="ml-auto">
          {nextDays !== null && (
            <span className="shrink-0 whitespace-nowrap rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
              D-{nextDays}
            </span>
          )}
            </div>
          </div>
          <p className="mt-0.5 text-[18px] font-bold leading-tight tracking-tight text-slate-900">
            {pct(remaining)}
            <span className="text-[12px] font-semibold text-slate-400">%</span>
          </p>
          <p className="text-[10.5px] leading-3.5 text-slate-400">{remaining.toLocaleString("ko-KR")}주</p>
        </div>
        <div className="text-right">
          <p className="flex items-center justify-end gap-1.5 text-[11.5px] font-semibold text-slate-600">
            해제 완료
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
          </p>
          <p className="mt-0.5 text-[18px] font-bold leading-tight tracking-tight text-slate-900">
            {pct(released)}
            <span className="text-[12px] font-semibold text-slate-400">%</span>
          </p>
          <p className="text-[10.5px] leading-3.5 text-slate-400">{released.toLocaleString("ko-KR")}주</p>
        </div>
      </div>

      <div
        className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-slate-900/10"
        role="img"
        aria-label={`전체 락업 물량 중 잔여 ${remainingShare.toFixed(1)}%, 해제 완료 ${releasedShare.toFixed(1)}%`}
      >
        <span className="h-full bg-amber-400" style={{ width: `${remainingShare}%` }} />
        <span className="h-full bg-emerald-400" style={{ width: `${releasedShare}%` }} />
      </div>
    </div>
  );
}
