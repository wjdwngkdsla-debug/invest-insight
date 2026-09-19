"use client";

import { useEffect, useState } from "react";
import type { IpoItem } from "@/lib/ipo";
import { IPO_STAGE_STYLE, ipoStageStatus, ipoToday, type IpoStageStatus } from "@/lib/ipo-stage";

// IPO 상태칩을 접속 시점 기준으로 계산 — 상장 D-11 같은 표기가 자정 넘어가면 즉시 갱신된다.
export function IpoStatusChip({ item }: { item: IpoItem }) {
  const [status, setStatus] = useState<IpoStageStatus | null>(null);
  useEffect(() => {
    const update = () => setStatus(ipoStageStatus(item, ipoToday()));
    const initial = window.setTimeout(update, 0);
    const timer = window.setInterval(update, 60000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [item]);

  const s = status ?? { label: "…", stage: "upcoming" as const };
  return (
    <span className={`inline-flex shrink-0 whitespace-nowrap rounded px-2 py-1 text-xs font-bold ${IPO_STAGE_STYLE[s.stage].color}`}>{s.label}</span>
  );
}
