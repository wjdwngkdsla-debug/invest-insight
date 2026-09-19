"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Search, X } from "lucide-react";
import type { IpoItem } from "@/lib/ipo";
import { matchesIpo, type IpoFilter } from "@/lib/ipo-filter";

const filters: { value: IpoFilter; label: string }[] = [
  { value: "active", label: "진행 일정" }, { value: "all", label: "전체 이력" },
  { value: "upcoming", label: "청약·수요예측 예정" }, { value: "forecast", label: "수요예측 중" },
  { value: "subscription", label: "청약 중" }, { value: "waiting", label: "상장 대기" },
  { value: "listed", label: "상장 완료" }, { value: "withdrawn", label: "공모 철회" },
  { value: "unscheduled", label: "일정 미정" },
];

export function IpoScheduleBrowser({ entries, initialToday }: { entries: { id: string; item: IpoItem; card: ReactNode }[]; initialToday: string }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<IpoFilter>("active");
  const [today, setToday] = useState(initialToday);
  useEffect(() => {
    const update = () => setToday(new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date()));
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, []);
  const visible = entries.filter(entry => matchesIpo(entry.item, query, filter, today));
  return <div>
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <div className="relative min-w-0 flex-1 basis-52">
        <Search size={16} aria-hidden className="absolute left-3 top-3 text-gray-400" />
        <input type="search" aria-label="IPO 기업명 또는 종목코드 검색" placeholder="기업명 · 종목코드" value={query} onChange={e => setQuery(e.target.value)} className="h-10 w-full rounded-md border border-gray-300 bg-white pl-9 pr-9 text-sm text-gray-900 focus:outline-blue-500 [&::-webkit-search-cancel-button]:appearance-none" />
        {query && <button type="button" title="검색 지우기" aria-label="검색 지우기" onClick={() => setQuery("")} className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center text-gray-500"><X size={16} /></button>}
      </div>
      <select aria-label="IPO 진행 상태" value={filter} onChange={e => setFilter(e.target.value as IpoFilter)} className="h-10 max-w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-700">
        {filters.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <span aria-live="polite" className="text-xs tabular-nums text-gray-500">{visible.length}개 기업</span>
    </div>
    <div className="space-y-3">{visible.map(entry => <div key={entry.id}>{entry.card}</div>)}</div>
    {!visible.length && <p className="border-y border-gray-200 py-12 text-center text-sm text-gray-500">조건에 맞는 IPO가 없습니다.</p>}
  </div>;
}
