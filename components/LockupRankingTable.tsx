"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { LockupPeriod, LockupRankingRow } from "@/lib/lockupRanking";
import { LOCKUP_PERIODS } from "@/lib/lockupRanking";
import { formatKrwEok } from "@/lib/format";

type SortKey = LockupPeriod | "marketCap";

function ReturnText({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-300">-</span>;
  return (
    <span className={`font-bold tabular-nums ${pct >= 0 ? "text-rose-600" : "text-blue-600"}`}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

function RankBadge({ rank }: { rank: number }) {
  const tone = rank === 1 ? "bg-amber-100 text-amber-700" : rank === 2 ? "bg-slate-200 text-slate-700" : rank === 3 ? "bg-orange-100 text-orange-700" : "bg-gray-100 text-slate-500";
  return <span className={`inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-[11.5px] font-bold tabular-nums ${tone}`}>{rank}</span>;
}

export function LockupRankingTable({ rows }: { rows: LockupRankingRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("1개월");
  const [asc, setAsc] = useState(false);

  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const av = sortKey === "marketCap" ? a.marketCap : a.returns[sortKey];
    const bv = sortKey === "marketCap" ? b.marketCap : b.returns[sortKey];
    if (av === null && bv === null) return a.name.localeCompare(b.name, "ko");
    if (av === null) return 1;
    if (bv === null) return -1;
    return asc ? av - bv : bv - av;
  }), [rows, sortKey, asc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setAsc((value) => !value);
    else { setSortKey(key); setAsc(false); }
  };
  const mark = (key: SortKey) => key === sortKey ? (asc ? " ↑" : " ↓") : "";

  if (!sorted.length) return <p className="rounded-[20px] border border-gray-200 bg-white p-6 text-sm text-gray-400">해제일 시세가 확인된 기관 확약 종목이 없습니다.</p>;

  return (
    <div className="space-y-3">
      <div className="hidden overflow-hidden rounded-[20px] border border-gray-200 bg-white shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)] md:block">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50/80 text-[11.5px] font-semibold text-slate-500">
              <th className="w-14 px-3 py-3 text-left">순위</th>
              <th className="px-3 py-3 text-left">종목</th>
              {LOCKUP_PERIODS.map((period) => (
                <th key={period} className="whitespace-nowrap px-3 py-3 text-right">
                  <button type="button" onClick={() => toggleSort(period)} className={period === sortKey ? "text-blue-600" : "hover:text-slate-900"}>
                    {period}{mark(period)}
                  </button>
                </th>
              ))}
              <th className="whitespace-nowrap px-3 py-3 text-right">
                <button type="button" onClick={() => toggleSort("marketCap")} className={sortKey === "marketCap" ? "text-blue-600" : "hover:text-slate-900"}>
                  시가총액{mark("marketCap")}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => (
              <tr key={row.code} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60">
                <td className="px-3 py-3"><RankBadge rank={index + 1} /></td>
                <td className="px-3 py-3"><Link href={`/stock/${row.code}`} className="font-semibold text-slate-900 underline-offset-4 hover:text-blue-700 hover:underline">{row.name}</Link></td>
                {LOCKUP_PERIODS.map((period) => <td key={period} className="px-3 py-3 text-right"><ReturnText pct={row.returns[period]} /></td>)}
                <td className="px-3 py-3 text-right tabular-nums text-slate-600">{formatKrwEok(row.marketCap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-2.5 md:hidden">
        {sorted.map((row, index) => (
          <li key={row.code} className="rounded-[18px] border border-gray-200 bg-white p-3.5">
            <div className="flex items-center gap-2"><RankBadge rank={index + 1} /><Link href={`/stock/${row.code}`} className="font-bold text-slate-900">{row.name}</Link><span className="ml-auto text-[11px] text-slate-400">{formatKrwEok(row.marketCap)}</span></div>
            <div className="mt-3 grid grid-cols-4 gap-1.5 rounded-xl bg-gray-50 p-2">
              {LOCKUP_PERIODS.map((period) => <div key={period} className="text-center"><p className="text-[10px] text-slate-400">{period}</p><p className="mt-0.5 text-[11px]"><ReturnText pct={row.returns[period]} /></p></div>)}
            </div>
          </li>
        ))}
      </ul>
      <p className="px-1 text-[11px] leading-relaxed text-slate-400">각 숫자는 기관 의무보유확약 물량이 거래 가능해진 날의 한국거래소 등락률입니다. 열 제목을 누르면 해당 기간 기준으로 순위가 바뀝니다.</p>
    </div>
  );
}
