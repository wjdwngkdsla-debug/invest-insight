"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { LockupPeriod, LockupRankingRow } from "@/lib/lockupRanking";
import { LOCKUP_PERIODS } from "@/lib/lockupRanking";
import { formatKrwEok } from "@/lib/format";

type SortKey = LockupPeriod | "marketCap" | "listingDate";

const DATE_INPUT =
  "rounded-lg border border-gray-200 bg-white px-2 py-1 text-[12px] font-medium text-slate-700 focus:border-blue-400 focus:outline-none";

/** 빈칸이 세 가지 뜻으로 섞이지 않게 문구를 나눈다. 기호 대신 말로 쓴다. */
function ReturnText({ pct, state }: { pct: number | null; state?: "none" | "upcoming" | "missing" | "ok" }) {
  if (pct === null) {
    if (state === "upcoming") {
      return <span className="text-[11px] text-slate-400" title="해제일이 아직 오지 않았습니다">해제 전</span>;
    }
    if (state === "missing") {
      return <span className="text-[11px] text-amber-600" title="해제일 시세를 아직 받지 못했습니다">확인 중</span>;
    }
    return <span className="text-[11px] text-slate-300" title="이 구간에는 기관 확약이 없었습니다">확약 없음</span>;
  }
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
  const bounds = useMemo(() => {
    const dates = rows.map((row) => row.listingDate).filter(Boolean).sort();
    return { min: dates[0] || "", max: dates[dates.length - 1] || "" };
  }, [rows]);
  const [query, setQuery] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("1개월");
  const [asc, setAsc] = useState(false);

  const filtered = useMemo(() => rows.filter((row) => {
    const keyword = query.trim();
    if (keyword && !row.name.includes(keyword)) return false;
    if (from && row.listingDate < from) return false;
    if (to && row.listingDate > to) return false;
    return true;
  }), [rows, query, from, to]);

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    if (sortKey === "listingDate") {
      const diff = a.listingDate.localeCompare(b.listingDate);
      return asc ? diff : -diff;
    }
    const av = sortKey === "marketCap" ? a.marketCap : a.returns[sortKey];
    const bv = sortKey === "marketCap" ? b.marketCap : b.returns[sortKey];
    if (av === null && bv === null) return a.name.localeCompare(b.name, "ko");
    if (av === null) return 1;
    if (bv === null) return -1;
    return asc ? av - bv : bv - av;
  }), [filtered, sortKey, asc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setAsc((value) => !value);
    else { setSortKey(key); setAsc(false); }
  };
  const mark = (key: SortKey) => key === sortKey ? (asc ? " ↑" : " ↓") : "";
  // 결과가 0건이어도 필터 줄은 계속 그린다. 여기서 조기 반환하면 검색창까지 사라져
  // 검색어를 지울 방법이 없어진다(빈 화면에 갇힘).
  const filteredOut = rows.length > 0 && sorted.length === 0;

  return (
    <div className="space-y-3">
      <div className="rounded-[20px] border border-gray-200 bg-white p-3.5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]">
        <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-2">
          <span className="text-[11.5px] font-semibold text-slate-400">상장일</span>
          <input type="date" value={from} min={bounds.min} max={to || bounds.max} onChange={(event) => setFrom(event.target.value)} className={DATE_INPUT} aria-label="상장일 시작" />
          <span className="text-[12px] text-slate-400">~</span>
          <input type="date" value={to} min={from || bounds.min} max={bounds.max} onChange={(event) => setTo(event.target.value)} className={DATE_INPUT} aria-label="상장일 종료" />
          {(from || to) && <button type="button" onClick={() => { setFrom(""); setTo(""); }} className="text-[12px] font-semibold text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline">기간 해제</button>}
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="종목명 검색" aria-label="종목명 검색" className="w-full rounded-md border border-gray-300 bg-white px-2.5 py-1 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-500 focus:outline-none sm:ml-2 sm:w-44" />
        </div>
      </div>
      {sorted.length === 0 && (
        <div className="rounded-[20px] border border-gray-200 bg-white p-6 text-sm text-gray-400">
          {filteredOut ? (
            <div className="flex flex-wrap items-center gap-2">
              <span>검색 조건에 맞는 종목이 없습니다.</span>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setFrom("");
                  setTo("");
                }}
                className="font-semibold text-blue-600 underline-offset-2 hover:underline"
              >
                조건 초기화
              </button>
            </div>
          ) : (
            "해제일 시세가 확인된 기관 확약 종목이 없습니다."
          )}
        </div>
      )}

      <div
        className={`overflow-hidden rounded-[20px] border border-gray-200 bg-white shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)] ${
          sorted.length === 0 ? "hidden" : "hidden md:block"
        }`}
      >
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50/80 text-[11.5px] font-semibold text-slate-500">
              <th className="w-14 px-3 py-3 text-left">순위</th>
              <th className="px-3 py-3 text-left">종목</th>
              <th className="whitespace-nowrap px-3 py-3 text-right"><button type="button" onClick={() => toggleSort("listingDate")} className={sortKey === "listingDate" ? "text-blue-600" : "hover:text-slate-900"}>상장일{mark("listingDate")}</button></th>
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
                <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums text-slate-500">{row.listingDate ? row.listingDate.slice(2).replaceAll("-", ".") : "-"}</td>
                {LOCKUP_PERIODS.map((period) => <td key={period} className="px-3 py-3 text-right"><ReturnText pct={row.returns[period]} state={row.state?.[period]} /></td>)}
                <td className="px-3 py-3 text-right tabular-nums text-slate-600">{formatKrwEok(row.marketCap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className={`space-y-2.5 ${sorted.length === 0 ? "hidden" : "md:hidden"}`}>
        {sorted.map((row, index) => (
          <li key={row.code} className="rounded-[18px] border border-gray-200 bg-white p-3.5">
            <div className="flex items-center gap-2"><RankBadge rank={index + 1} /><Link href={`/stock/${row.code}`} className="font-bold text-slate-900">{row.name}</Link><span className="text-[10.5px] tabular-nums text-slate-400">{row.listingDate ? row.listingDate.slice(2).replaceAll("-", ".") : "-"}</span><span className="ml-auto text-[11px] text-slate-400">{formatKrwEok(row.marketCap)}</span></div>
            <div className="mt-3 grid grid-cols-4 gap-1.5 rounded-xl bg-gray-50 p-2">
              {LOCKUP_PERIODS.map((period) => <div key={period} className="text-center"><p className="text-[10px] text-slate-400">{period}</p><p className="mt-0.5 text-[11px]"><ReturnText pct={row.returns[period]} state={row.state?.[period]} /></p></div>)}
            </div>
          </li>
        ))}
      </ul>
      <p className="px-1 text-[11px] leading-relaxed text-slate-400">
        각 숫자는 기관 의무보유확약 물량이 거래 가능해진 날의 한국거래소 등락률입니다. 열 제목을 누르면 해당 기간 기준으로
        순위가 바뀝니다. <span className="text-slate-400">확약 없음</span>은 수요예측에서 그 구간을 확약한 기관이 없었다는
        뜻이고, <span className="text-slate-400">해제 전</span>은 해제일이 아직 오지 않은 구간입니다.
      </p>
    </div>
  );
}
