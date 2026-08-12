"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { LockupRankingRow } from "@/lib/lockupRanking";
import { LOCKUP_PERIODS } from "@/lib/lockupRanking";
import { formatKrwEok } from "@/lib/format";

type MarketKey = "all" | "코스피" | "코스닥";
type PeriodKey = "all" | (typeof LOCKUP_PERIODS)[number];
type SortKey = "flucRt" | "pct" | "qty" | "marketCap" | "releaseDate";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "flucRt", label: "해제일 등락률" },
  { key: "pct", label: "해제 비중" },
  { key: "qty", label: "해제 물량" },
  { key: "marketCap", label: "시가총액" },
  { key: "releaseDate", label: "해제일" },
];

const CHIP_BASE = "rounded-full px-3 py-1 text-[12px] font-semibold transition-colors";
const CHIP_ON = "bg-blue-600 text-white";
const CHIP_OFF = "border border-gray-200 bg-white text-slate-600 hover:bg-gray-50";
const DATE_INPUT =
  "rounded-lg border border-gray-200 bg-white px-2 py-1 text-[12px] font-medium text-slate-700 focus:border-blue-400 focus:outline-none";

function yymmdd(date: string): string {
  return date ? date.slice(2).replaceAll("-", ".") : "-";
}

function ReturnText({ pct, className = "" }: { pct: number | null; className?: string }) {
  if (pct === null) return <span className="text-slate-300">-</span>;
  const up = pct >= 0;
  return (
    <span className={`font-bold tabular-nums ${up ? "text-rose-600" : "text-blue-600"} ${className}`}>
      {up ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
  );
}

function RankBadge({ rank }: { rank: number }) {
  const tone =
    rank === 1
      ? "bg-amber-100 text-amber-700"
      : rank === 2
        ? "bg-slate-200 text-slate-700"
        : rank === 3
          ? "bg-orange-100 text-orange-700"
          : "bg-gray-100 text-slate-500";
  return (
    <span className={`inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-[11.5px] font-bold tabular-nums ${tone}`}>
      {rank}
    </span>
  );
}

function PeriodTag({ period }: { period: string }) {
  return (
    <span className="ml-1.5 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">{period}</span>
  );
}

export function LockupRankingTable({ rows }: { rows: LockupRankingRow[] }) {
  const bounds = useMemo(() => {
    const dates = rows.map((row) => row.releaseDate).filter(Boolean).sort();
    return { min: dates[0] || "", max: dates[dates.length - 1] || "" };
  }, [rows]);

  const [query, setQuery] = useState("");
  const [market, setMarket] = useState<MarketKey>("all");
  const [period, setPeriod] = useState<PeriodKey>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("flucRt");
  const [asc, setAsc] = useState(false);

  const keyword = query.trim();
  const filtered = useMemo(
    () =>
      rows.filter((row) => {
        if (keyword && !row.name.includes(keyword)) return false;
        if (market !== "all" && row.market !== market) return false;
        if (period !== "all" && row.period !== period) return false;
        if (from && row.releaseDate < from) return false;
        if (to && row.releaseDate > to) return false;
        return true;
      }),
    [rows, keyword, market, period, from, to],
  );

  const sorted = useMemo(
    () =>
      [...filtered].sort((a, b) => {
        if (sortKey === "releaseDate") {
          const diff = a.releaseDate.localeCompare(b.releaseDate);
          return asc ? diff : -diff;
        }
        const diff = a[sortKey] - b[sortKey];
        return asc ? diff : -diff;
      }),
    [filtered, sortKey, asc],
  );

  const summary = useMemo(() => {
    if (filtered.length === 0) return null;
    const total = filtered.reduce((sum, row) => sum + row.flucRt, 0);
    const up = filtered.filter((row) => row.flucRt > 0).length;
    return {
      count: filtered.length,
      average: total / filtered.length,
      upShare: (up / filtered.length) * 100,
    };
  }, [filtered]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setAsc((prev) => !prev);
      return;
    }
    setSortKey(key);
    setAsc(false);
  };
  const sortMark = (key: SortKey) => (key === sortKey ? (asc ? " ↑" : " ↓") : "");
  const dateFiltered = Boolean(from || to);

  return (
    <div className="space-y-4">
      {/* 필터 한 줄 — 시장 · 확약 기간 · 해제일 기간(캘린더) · 종목명 검색 */}
      <div className="rounded-[20px] border border-gray-200 bg-white p-3.5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {(["all", "코스피", "코스닥"] as MarketKey[]).map((key) => (
            <button key={key} type="button" onClick={() => setMarket(key)} className={`${CHIP_BASE} ${market === key ? CHIP_ON : CHIP_OFF}`}>
              {key === "all" ? "전체" : key}
            </button>
          ))}
          <span aria-hidden className="mx-1 hidden h-4 w-px bg-gray-200 sm:block" />
          {(["all", ...LOCKUP_PERIODS] as PeriodKey[]).map((key) => (
            <button key={key} type="button" onClick={() => setPeriod(key)} className={`${CHIP_BASE} ${period === key ? CHIP_ON : CHIP_OFF}`}>
              {key === "all" ? "전체 확약" : key}
            </button>
          ))}
          <span aria-hidden className="mx-1 hidden h-4 w-px bg-gray-200 sm:block" />
          <span className="text-[11.5px] font-semibold text-slate-400">해제일</span>
          <input
            type="date"
            value={from}
            min={bounds.min}
            max={to || bounds.max}
            onChange={(event) => setFrom(event.target.value)}
            className={DATE_INPUT}
            aria-label="해제일 시작"
          />
          <span className="text-[12px] text-slate-400">~</span>
          <input
            type="date"
            value={to}
            min={from || bounds.min}
            max={bounds.max}
            onChange={(event) => setTo(event.target.value)}
            className={DATE_INPUT}
            aria-label="해제일 종료"
          />
          {dateFiltered && (
            <button
              type="button"
              onClick={() => {
                setFrom("");
                setTo("");
              }}
              className="text-[12px] font-semibold text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline"
            >
              기간 해제
            </button>
          )}
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="종목명 검색"
            aria-label="종목명 검색"
            className="w-full rounded-md border border-gray-300 bg-white px-2.5 py-1 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-500 focus:outline-none sm:ml-auto sm:w-44"
          />
        </div>
      </div>

      {/* 요약 — 선택 구간의 해제일 주가 반응 */}
      {summary && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">해제 건수</p>
            <p className="mt-0.5 text-[17px] font-bold tabular-nums text-slate-900">{summary.count}건</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">평균 등락률</p>
            <p className="mt-0.5 text-[17px]">
              <ReturnText pct={summary.average} />
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">상승 비율</p>
            <p className="mt-0.5 flex items-baseline gap-1 text-[17px]">
              <span className="font-bold tabular-nums text-slate-900">{summary.upShare.toFixed(0)}%</span>
              <span className="text-[10.5px] font-medium text-slate-400">해제일에 오른 비중</span>
            </p>
          </div>
        </div>
      )}

      {sorted.length === 0 ? (
        <p className="rounded-[20px] border border-gray-200 bg-white p-6 text-sm text-gray-400">
          선택한 조건에 해당하는 해제 건이 없습니다.
        </p>
      ) : (
        <>
          {/* 데스크톱: 표 */}
          <div className="hidden overflow-hidden rounded-[20px] border border-gray-200 bg-white shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)] md:block">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50/80 text-[11.5px] font-semibold text-slate-500">
                  <th className="w-14 px-3 py-2.5 text-left">순위</th>
                  <th className="px-3 py-2.5 text-left">종목</th>
                  {COLUMNS.map((column) => (
                    <th key={column.key} className="whitespace-nowrap px-3 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className={`transition-colors hover:text-slate-900 ${column.key === sortKey ? "text-blue-600" : ""}`}
                      >
                        {column.label}
                        {sortMark(column.key)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, index) => (
                  <tr key={`${row.code}-${row.period}-${row.releaseDate}`} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60">
                    <td className="px-3 py-2.5">
                      <RankBadge rank={index + 1} />
                    </td>
                    <td className="px-3 py-2.5">
                      <Link href={`/stock/${row.code}`} className="font-semibold text-slate-900 underline-offset-4 hover:text-blue-700 hover:underline">
                        {row.name}
                      </Link>
                      <PeriodTag period={row.period} />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <ReturnText pct={row.flucRt} />
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{row.pct.toFixed(2)}%</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{row.qty.toLocaleString("ko-KR")}주</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{formatKrwEok(row.marketCap)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">{yymmdd(row.releaseDate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 모바일: 카드 목록 */}
          <ul className="space-y-2.5 md:hidden">
            {sorted.map((row, index) => (
              <li
                key={`${row.code}-${row.period}-${row.releaseDate}`}
                className="rounded-[18px] border border-gray-200 bg-white p-3.5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <RankBadge rank={index + 1} />
                    <Link href={`/stock/${row.code}`} className="truncate font-bold text-slate-900">
                      {row.name}
                    </Link>
                    <PeriodTag period={row.period} />
                  </div>
                  <ReturnText pct={row.flucRt} className="shrink-0 text-[17px]" />
                </div>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 rounded-xl border border-gray-200 bg-gray-50/80 px-3 py-2 text-[11px]">
                  <span className="text-slate-500">
                    해제 비중 <span className="font-semibold tabular-nums text-slate-700">{row.pct.toFixed(2)}%</span>
                  </span>
                  <span className="text-slate-500">
                    물량 <span className="font-semibold tabular-nums text-slate-700">{row.qty.toLocaleString("ko-KR")}주</span>
                  </span>
                  <span className="text-slate-500">
                    시총 <span className="font-semibold tabular-nums text-slate-700">{formatKrwEok(row.marketCap)}</span>
                  </span>
                  <span className="text-slate-500">
                    해제일 <span className="font-semibold tabular-nums text-slate-700">{yymmdd(row.releaseDate)}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="px-1 text-[11px] leading-relaxed text-slate-400">
        <span className="font-semibold text-slate-500">해제일 등락률</span>은 기관 의무보유확약 물량이 풀린 날, 그 종목이
        전 거래일 종가 대비 얼마나 움직였는지입니다. 확약 기간(15일·1개월·3개월·6개월)은 수요예측 때 정해지므로 종목끼리
        같은 조건으로 비교할 수 있습니다.
        <br />
        등락률은 한국거래소가 발표한 값을 그대로 씁니다. 권리락이 있던 날은 전일 종가가 아니라 기준가 대비로 계산된
        값입니다. 해제 당일 주가는 확약 물량 외에 시장 전체 흐름과 개별 재료에도 함께 움직인다는 점을 감안해 보세요.
      </p>
    </div>
  );
}
