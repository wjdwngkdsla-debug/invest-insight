"use client";

import { useState } from "react";
import { Button, FluentProvider, webLightTheme } from "@fluentui/react-components";
import type { IpoRankingRow } from "@/lib/ranking";
import type { LockupRankingRow } from "@/lib/lockupRanking";
import { IpoRankingTable } from "@/components/IpoRankingTable";
import { LockupRankingTable } from "@/components/LockupRankingTable";

type View = "ipo" | "lockup";

export function RankingSwitcher({ ipoRows, lockupRows, priceDate, initialView = "ipo" }: { ipoRows: IpoRankingRow[]; lockupRows: LockupRankingRow[]; priceDate: string; initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
  return (
    <FluentProvider theme={webLightTheme} className="contents">
    <div className="space-y-4">
      <div className="flex gap-2 overflow-x-auto pb-1 sm:items-center sm:overflow-visible sm:pb-0">
        <Button type="button" appearance={view === "ipo" ? "primary" : "secondary"} shape="rounded" onClick={() => setView("ipo")} className="!h-9 !shrink-0 !rounded-full !px-4 !text-[12px] !font-bold sm:!text-[13px]">공모주 수익률</Button>
        <Button type="button" appearance={view === "lockup" ? "primary" : "secondary"} shape="rounded" onClick={() => setView("lockup")} className="!h-9 !shrink-0 !rounded-full !px-4 !text-[12px] !font-bold sm:!text-[13px]">기관 락업 해제일 등락률</Button>
      </div>
      {view === "ipo" ? <IpoRankingTable rows={ipoRows} priceDate={priceDate} /> : <LockupRankingTable rows={lockupRows} />}
    </div>
    </FluentProvider>
  );
}
