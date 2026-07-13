"use client";

import { useEffect, useState } from "react";
import { ipoStatus, type IpoItem, type IpoStatus, type IpoTone } from "@/lib/ipo";

// IPO 상태칩을 접속 시점 기준으로 계산 — 상장 D-11 같은 표기가 자정 넘어가면 즉시 갱신된다.
const TONE_CLASS: Record<IpoTone, string> = {
  active: "bg-red-100 text-red-600",
  waiting: "bg-blue-100 text-blue-600",
  done: "bg-gray-100 text-gray-500",
};

export function IpoStatusChip({ item }: { item: IpoItem }) {
  const [status, setStatus] = useState<IpoStatus | null>(null);
  useEffect(() => setStatus(ipoStatus(item)), [item]);

  const s = status ?? { label: "…", tone: "waiting" as IpoTone };
  return (
    <span className={`inline-flex shrink-0 rounded px-2 py-1 text-xs font-bold ${TONE_CLASS[s.tone]}`}>{s.label}</span>
  );
}
