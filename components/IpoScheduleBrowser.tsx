"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { IpoItem } from "@/lib/ipo";
import { IPO_STAGE_STYLE, compareIpoStages, ipoToday, matchesIpoStage, type IpoStageFilter } from "@/lib/ipo-stage";

const filters: { value: IpoStageFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "listing", label: "상장" },
  { value: "subscription", label: "청약" },
  { value: "forecast", label: "수요예측" },
  { value: "upcoming", label: "공모예정" },
];

export function IpoScheduleBrowser({ entries, initialToday }: {
  entries: { id: string; item: IpoItem; card: ReactNode; archived: boolean }[];
  initialToday: string;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<IpoStageFilter>("all");
  const [showHistory, setShowHistory] = useState(false);
  const [today, setToday] = useState(initialToday);
  useEffect(() => {
    const update = () => setToday(ipoToday());
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, []);
  const visible = entries
    .filter(entry => matchesIpoStage(entry.item, query, filter, today, showHistory, entry.archived))
    .sort((a, b) => compareIpoStages(a.item, b.item, today, showHistory));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search" aria-label="IPO 종목명 검색" placeholder="종목명 검색"
          value={query} onChange={event => setQuery(event.target.value)}
          className="h-9 min-w-0 flex-1 basis-[180px] rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-blue-500 sm:max-w-[220px]"
        />
        <button type="button" onClick={() => { setShowHistory(value => !value); setQuery(""); setFilter("all"); }}
          className="shrink-0 whitespace-nowrap rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 sm:order-3 sm:ml-auto">
          {showHistory ? "진행 일정 보기" : "이전 이력 보기"}
        </button>
        {!showHistory && (
          <div role="group" aria-label="IPO 단계 필터" className="flex w-full flex-wrap items-center gap-1.5 sm:w-auto">
            {filters.map(option => {
              const selected = filter === option.value;
              const style = option.value === "all" ? null : IPO_STAGE_STYLE[option.value];
              return <button key={option.value} type="button" aria-pressed={selected} onClick={() => setFilter(option.value)}
                className={`inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-[11px] font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ${style ? `${style.color} ${selected ? "ring-1 ring-current" : "hover:brightness-95"}` : selected ? "bg-slate-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
                {option.label}
              </button>;
            })}
          </div>
        )}
      </div>
      <div className="space-y-3">{visible.map(entry => <div key={entry.id}>{entry.card}</div>)}</div>
      {visible.length === 0 && <p role="status" className="border-y border-gray-200 py-12 text-center text-sm text-gray-500">{query || filter !== "all" ? "조건에 맞는 종목이 없습니다." : showHistory ? "이전 IPO 이력이 없습니다." : "진행 중인 공모가 없습니다."}</p>}
    </div>
  );
}
