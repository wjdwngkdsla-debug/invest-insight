"use client";

import { useState } from "react";
import type { IpoRankingRow } from "@/lib/ranking";
import type { LockupRankingRow } from "@/lib/lockupRanking";
import { IpoRankingTable } from "@/components/IpoRankingTable";
import { LockupRankingTable } from "@/components/LockupRankingTable";

type View = "ipo" | "lockup";
const CHIP = "rounded-full px-4 py-2 text-[13px] font-bold transition-colors";

export function RankingSwitcher({ ipoRows, lockupRows, priceDate, initialView = "ipo" }: { ipoRows: IpoRankingRow[]; lockupRows: LockupRankingRow[]; priceDate: string; initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setView("ipo")} className={`${CHIP} ${view === "ipo" ? "bg-blue-600 text-white" : "border border-gray-200 bg-white text-slate-600 hover:bg-gray-50"}`}>공모주 수익률</button>
        <button type="button" onClick={() => setView("lockup")} className={`${CHIP} ${view === "lockup" ? "bg-blue-600 text-white" : "border border-gray-200 bg-white text-slate-600 hover:bg-gray-50"}`}>기관 락업 해제일 등락률</button>
      </div>
      {view === "ipo" ? <IpoRankingTable rows={ipoRows} priceDate={priceDate} /> : <LockupRankingTable rows={lockupRows} />}
    </div>
  );
}
