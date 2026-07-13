"use client";

import { useEffect, useState, type ReactNode } from "react";

// 기준 날짜가 접속 시점(KST) 기준으로 지났으면 자식을 숨긴다.
// 오늘(당일)은 노출, 어제 이하만 숨김 → "오늘 지나면 사라짐". 정적 배포 유지, 마운트 후 계산.
function kstDayNumber(ms: number): number {
  return Math.floor((ms + 9 * 60 * 60 * 1000) / 86400000);
}

function isPast(dateStr: string): boolean {
  const target = kstDayNumber(Date.parse(`${dateStr}T00:00:00+09:00`));
  return target < kstDayNumber(Date.now());
}

export function PastDateGate({ date, children }: { date?: string; children: ReactNode }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (date) setHidden(isPast(date));
  }, [date]);

  if (hidden) return null;
  return <>{children}</>;
}
