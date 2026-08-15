"use client";

import { useMemo, useState } from "react";
import type { StockLockup } from "@/lib/types";
import type { UpcomingGroup } from "@/lib/data";
import { listingShares } from "@/lib/returns";
import { BackButton } from "@/components/BackButton";
import { StockEventSections } from "@/components/StockEventSections";
import { StockHero } from "@/components/StockHero";

function adjustmentMultiplier(stock: StockLockup): number {
  const factor = stock.ipo_adjustment_factor || 1;
  if (!stock.adjustment_events?.length || !factor || Math.abs(factor - 1) < 0.001) return 1;
  return 1 / factor;
}

function formatMultiple(value: number): string {
  if (!Number.isFinite(value)) return "";
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(2).replace(/\.?0+$/, "");
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
      <div className="mb-4 flex items-center justify-between gap-3">
        <BackButton />
        {hasAdjustment && (
          <div className="flex min-w-0 items-center justify-end gap-2">
            {adjustedMode && (
              <span className="truncate text-[11px] font-semibold text-blue-600 md:text-xs">
                주식수 {formatMultiple(multiplier)}배 증가
              </span>
            )}
            <button
              type="button"
              onClick={() => setAdjustedMode(!adjustedMode)}
              className={`h-9 shrink-0 rounded-full border px-3.5 text-[12px] font-semibold transition-colors md:px-4 ${
                adjustedMode
                  ? "border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
                  : "border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-100"
              }`}
            >
              {adjustedMode ? "상장 당시 기준" : "주식수 조정 반영"}
            </button>
          </div>
        )}
      </div>
      <StockHero
        stock={stock}
        updated={updated}
        initialNow={initialNow}
        adjustedMode={adjustedMode}
        quantityFactor={quantityFactor}
        displayShares={displayShares}
      />
      <h2 className="sr-only">{stock.name} 락업 해제 일정</h2>
      <section className="mt-4 rounded-[24px] border border-slate-200/70 bg-slate-50/70 px-4 py-5 shadow-[0_2px_20px_-14px_rgba(15,23,42,0.4)] md:mt-5 md:rounded-[32px] md:px-8 md:py-7">
        <StockEventSections
          groups={groups}
          initialNow={initialNow}
          shares={displayShares}
          quantityFactor={quantityFactor}
          adjustedMode={adjustedMode}
        />
      </section>
    </>
  );
}
