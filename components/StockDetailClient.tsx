"use client";

import { useMemo, useState } from "react";
import type { StockLockup } from "@/lib/types";
import type { UpcomingGroup } from "@/lib/data";
import { listingShares } from "@/lib/returns";
import { StockEventSections } from "@/components/StockEventSections";
import { StockHero } from "@/components/StockHero";

function adjustmentMultiplier(stock: StockLockup): number {
  const factor = stock.ipo_adjustment_factor || 1;
  if (!stock.adjustment_events?.length || !factor || Math.abs(factor - 1) < 0.001) return 1;
  return 1 / factor;
}

export function StockDetailClient({
  stock,
  groups,
  updated,
  initialNow,
}: {
  stock: StockLockup;
  groups: UpcomingGroup[];
  updated: string;
  initialNow: number;
}) {
  const multiplier = adjustmentMultiplier(stock);
  const hasAdjustment = Math.abs(multiplier - 1) >= 0.001;
  const [adjustedMode, setAdjustedMode] = useState(false);
  const quantityFactor = adjustedMode && hasAdjustment ? multiplier : 1;
  const baseShares = listingShares(stock);
  const displayShares = useMemo(
    () => Math.round(baseShares * quantityFactor),
    [baseShares, quantityFactor],
  );

  return (
    <>
      <StockHero
        stock={stock}
        updated={updated}
        initialNow={initialNow}
        adjustedMode={adjustedMode}
        onAdjustedModeChange={setAdjustedMode}
        quantityFactor={quantityFactor}
        displayShares={displayShares}
      />
      <h2 className="sr-only">{stock.name} 락업 해제 일정</h2>
      <section className="mt-4 rounded-[24px] border border-slate-200/70 bg-slate-50/70 px-4 py-5 shadow-[0_2px_20px_-14px_rgba(15,23,42,0.4)] md:mt-5 md:rounded-[32px] md:px-8 md:py-7">
        <StockEventSections
          groups={groups}
          initialNow={initialNow}
          shares={displayShares}
          adjustmentEvents={stock.adjustment_events}
          quantityFactor={quantityFactor}
          adjustedMode={adjustedMode}
        />
      </section>
    </>
  );
}
