"use client";

import { useEffect, useState } from "react";

// D-day를 접속 시점(클라이언트) 기준으로 계산 — 배치·재배포 없이 자정 넘어가면 즉시 갱신된다.
function kstDayNumber(ms: number): number {
  return Math.floor((ms + 9 * 60 * 60 * 1000) / 86400000);
}

function dday(dateStr: string): number {
  const target = kstDayNumber(Date.parse(`${dateStr}T00:00:00+09:00`));
  return target - kstDayNumber(Date.now());
}

export function DdayBadge({ date }: { date: string }) {
  // 서버/클라이언트 날짜 불일치(하이드레이션 오류) 방지: 마운트 후 계산
  const [days, setDays] = useState<number | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setDays(dday(date)), 0);
    return () => window.clearTimeout(timer);
  }, [date]);

  if (days === null) {
    return (
      <span className="inline-flex shrink-0 animate-pulse rounded bg-gray-100 px-2 py-1 text-xs font-bold text-gray-300">
        D-·
      </span>
    );
  }
  const isNear = days <= 3;
  const label = days === 0 ? "D-DAY" : days < 0 ? `D+${-days}` : `D-${days}`;
  return (
    <span
      className={`inline-flex shrink-0 rounded px-2 py-1 text-xs font-bold ${
        isNear ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
      }`}
    >
      {label}
    </span>
  );
}
