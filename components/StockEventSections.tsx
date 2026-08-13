"use client";

import { useEffect, useMemo, useState } from "react";
import type { UpcomingGroup } from "@/lib/data";

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 86_400_000;
const PERIOD_PRIORITY = ["15일", "1개월", "2개월", "3개월", "6개월", "12개월", "1년", "24개월", "2년", "30개월", "36개월", "3년"];

function kstDayNumber(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS);
}

function daysUntil(date: string, nowMs: number): number {
  return kstDayNumber(Date.parse(`${date}T00:00:00+09:00`)) - kstDayNumber(nowMs);
}

function nextKstMidnightDelay(nowMs: number): number {
  const shifted = new Date(nowMs + KST_OFFSET_MS);
  const nextMidnightUtc = Date.UTC(
    shifted.getUTCFullYear(),
    shifted.getUTCMonth(),
    shifted.getUTCDate() + 1,
  ) - KST_OFFSET_MS;
  return Math.max(1_000, nextMidnightUtc - nowMs + 250);
}

function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}

function groupTitle(group: UpcomingGroup): string {
  const period = PERIOD_PRIORITY.find((candidate) => group.periods.includes(candidate));
  if (period) return `${period} 락업 해제`;
  if (group.periods.length === 1) return `${group.periods[0]} 락업 해제`;
  return "락업 해제";
}

function Breakdown({ group }: { group: UpcomingGroup }) {
  if (group.breakdown.length === 0) return null;
  return (
    <div className="mt-1 space-y-1 text-right text-xs leading-snug text-gray-400">
      {group.breakdown.map((item) => {
        return (
          <div key={item.category}>
            <p>
              <span className="mr-1">{item.category}</span>
              <span className="font-medium text-gray-500">
                {formatQty(item.qty)}{item.unit || "주"} ({item.pct}%)
              </span>
            </p>
          </div>
        );
      })}
    </div>
  );
}

function EventRow({ group, tone, nowMs }: { group: UpcomingGroup; tone: "upcoming" | "past"; nowMs: number }) {
  const days = daysUntil(group.tradable_date, nowMs);
  const status = days >= 0 ? "예정" : "해제완료";
  const badge = days === 0 ? "D-DAY" : `D-${days}`;
  const imminent = days <= 3;
  return (
    <li
      className={`overflow-hidden rounded-2xl border shadow-[0_2px_10px_rgba(15,23,42,0.04)] ${
        tone === "upcoming" ? "border-blue-100 bg-white" : "border-gray-200 bg-gray-50/80"
      }`}
    >
      <div className="flex items-stretch">
        {/* 좌측 컬러 바 — 예정(파랑/임박 빨강) vs 지난(회색) 한눈 구분 */}
        <span
          aria-hidden
          className={`w-1.5 shrink-0 ${tone === "upcoming" ? (imminent ? "bg-red-500" : "bg-blue-500") : "bg-gray-300"}`}
        />
        <div className="flex flex-1 items-start justify-between gap-4 px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className={`flex flex-wrap items-center gap-2 font-semibold ${tone === "upcoming" ? "text-gray-900" : "text-gray-500"}`}>
              {tone === "upcoming" && (
                <span className={`rounded-md px-2 py-1 text-xs font-bold ${imminent ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"}`}>
                  {badge}
                </span>
              )}
              {groupTitle(group)}
            </p>
            <p className="mt-1 text-xs text-gray-400">{group.date_display}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className={`rounded-full px-2 py-0.5 font-medium ${status === "예정" ? "bg-blue-50 text-blue-700" : "bg-gray-200/70 text-gray-500"}`}>
                {status}
              </span>
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p className={`font-semibold ${tone === "upcoming" ? "text-gray-900" : "text-gray-500"}`}>
              {formatQty(group.qty)}{group.unit} ({group.pct}%)
            </p>
            <Breakdown group={group} />
          </div>
        </div>
      </div>
    </li>
  );
}

export function StockEventSections({
  groups,
  initialNow,
  shares,
}: {
  groups: UpcomingGroup[];
  initialNow: number;
  shares: number;
}) {
  const [nowMs, setNowMs] = useState(initialNow);
  useEffect(() => {
    let timer = 0;
    const refresh = () => {
      const now = Date.now();
      setNowMs(now);
      timer = window.setTimeout(refresh, nextKstMidnightDelay(now));
    };
    timer = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const { upcoming, past } = useMemo(() => {
    const sorted = [...groups].sort((a, b) => a.tradable_date.localeCompare(b.tradable_date));
    return {
      upcoming: sorted.filter((group) => daysUntil(group.tradable_date, nowMs) >= 0),
      past: sorted.filter((group) => daysUntil(group.tradable_date, nowMs) < 0),
    };
  }, [groups, nowMs]);

  return (
    <>
      {upcoming.length > 0 && (
        <section className="mb-9">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-2 text-lg font-bold">
              <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-blue-500" />
              예정된 해제
              <span className="text-sm font-medium text-gray-400">{upcoming.length}건</span>
            </h2>
            {shares > 0 && (
              <p className="text-sm text-gray-400">
                상장주식수 <span className="font-semibold tabular-nums text-gray-600">{formatQty(shares)}주</span>
              </p>
            )}
          </div>
          <ul className="space-y-3">
            {upcoming.map((group) => <EventRow key={group.tradable_date} group={group} tone="upcoming" nowMs={nowMs} />)}
          </ul>
        </section>
      )}

      <section>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lg font-bold text-gray-500">
            <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-gray-300" />
            지난 해제 내역
            {past.length > 0 && <span className="text-sm font-medium text-gray-400">{past.length}건</span>}
          </h2>
          {upcoming.length === 0 && shares > 0 && (
            <p className="text-sm text-gray-400">
              상장주식수 <span className="font-semibold tabular-nums text-gray-600">{formatQty(shares)}주</span>
            </p>
          )}
        </div>
        {past.length === 0 ? (
          <p className="text-sm text-gray-400">아직 지난 해제 내역이 없습니다.</p>
        ) : (
          <ul className="space-y-3">
            {past.map((group) => <EventRow key={group.tradable_date} group={group} tone="past" nowMs={nowMs} />)}
          </ul>
        )}
      </section>
    </>
  );
}
