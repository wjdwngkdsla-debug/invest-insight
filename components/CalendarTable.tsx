"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { displayStatus, type FlatRow } from "@/lib/data";

// 화면용 합산 행 — 같은 종목·같은 해제일의 IPO기관/기존주주 물량을 하나로 합친다
interface MergedRow {
  code: string;
  name: string;
  listing_date: string;
  tradable_date: string;
  date_display: string;
  qty: number;
  pct: number;
  scale: number; // 해제규모(원) = 기준일 종가 × 합산 물량
  periods: string;
  periodOrder: number;
  marketCap: number;
}

type SortKey = "name" | "listing_date" | "tradable_date" | "scale" | "qty" | "pct" | "period" | "marketCap";
type SortDir = "asc" | "desc";

const PERIOD_ORDER: Record<string, number> = {
  "15일": 0,
  "1개월": 1,
  "2개월": 2,
  "3개월": 3,
  "6개월": 4,
  "12개월": 5,
  "1년": 6,
  "24개월": 7,
  "2년": 8,
  "30개월": 9,
  "36개월": 10,
  "3년": 11,
};

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "name", label: "종목" },
  { key: "listing_date", label: "상장일" },
  { key: "tradable_date", label: "해제일" },
  { key: "scale", label: "해제규모", align: "right" },
  { key: "qty", label: "락업 해제 물량", align: "right" },
  { key: "pct", label: "비중", align: "right" },
  { key: "period", label: "기간" },
  { key: "marketCap", label: "시가총액", align: "right" },
];

function formatEok(won: number): string {
  const eok = won / 1e8;
  if (eok >= 10) return `${Math.round(eok).toLocaleString("ko-KR")}억원`;
  return `${(Math.round(eok * 10) / 10).toLocaleString("ko-KR")}억원`;
}

function mergeRows(rows: FlatRow[]): MergedRow[] {
  const map = new Map<string, MergedRow>();
  for (const row of rows) {
    const key = `${row.code}|${row.tradable_date}`;
    const existing = map.get(key);
    if (existing) {
      existing.qty += row.qty;
      existing.pct = Math.round((existing.pct + row.pct) * 100) / 100;
      existing.scale = existing.qty * row.close_price;
      if (!existing.periods.split("·").includes(row.period)) {
        existing.periods = `${existing.periods}·${row.period}`;
        existing.periodOrder = Math.min(existing.periodOrder, PERIOD_ORDER[row.period] ?? 999);
      }
    } else {
      map.set(key, {
        code: row.code,
        name: row.name,
        listing_date: row.listing_date,
        tradable_date: row.tradable_date,
        date_display: row.date_display,
        qty: row.qty,
        pct: row.pct,
        scale: row.qty * row.close_price,
        periods: row.period,
        periodOrder: PERIOD_ORDER[row.period] ?? 999,
        marketCap: row.marketCap,
      });
    }
  }
  return [...map.values()];
}

function compare(a: MergedRow, b: MergedRow, key: SortKey): number {
  switch (key) {
    case "name":
      return a.name.localeCompare(b.name, "ko-KR");
    case "listing_date":
    case "tradable_date":
      return a[key].localeCompare(b[key]);
    case "period":
      return a.periodOrder - b.periodOrder;
    case "scale":
      return a.scale - b.scale;
    case "qty":
      return a.qty - b.qty;
    case "pct":
      return a.pct - b.pct;
    case "marketCap":
      return a.marketCap - b.marketCap;
  }
}

// CSV는 화면 합산과 무관하게 원본 분리 데이터(구분·상태 포함)를 그대로 내보낸다
function downloadCsv(rows: FlatRow[], priceDate?: string) {
  const marketCapHeader = priceDate ? `시가총액(${priceDate.slice(2)})` : "시가총액";
  const headers = [
    "종목",
    "종목코드",
    "시장",
    "상장일",
    "구분",
    "기간",
    "해제일",
    "락업 해제 물량",
    "비중(상장 주식 대비 %)",
    marketCapHeader,
    "상태",
  ];
  const lines = [
    headers.join(","),
    ...rows.map((r) =>
      [
        r.name,
        r.code,
        r.market,
        r.listing_date,
        r.category,
        r.period,
        r.date_display,
        r.qty,
        r.pct,
        r.marketCap,
        displayStatus(r.tradable_date),
      ]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
        .join(",")
    ),
  ];
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `락업해제일정_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const PAGE_SIZE = 20;

export function CalendarTable({ rows, priceDate }: { rows: FlatRow[]; priceDate?: string }) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("tradable_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);

  // 검색 → 합산 → 정렬 → 페이지 순서로 처리
  const filteredRaw = useMemo(() => {
    const q = query.trim();
    return q ? rows.filter((row) => row.name.includes(q)) : rows;
  }, [rows, query]);

  const merged = useMemo(() => mergeRows(filteredRaw), [filteredRaw]);

  const sorted = useMemo(() => {
    const copy = [...merged];
    copy.sort((a, b) => compare(a, b, sortKey) * (sortDir === "asc" ? 1 : -1));
    return copy;
  }, [merged, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paged = useMemo(
    () => sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [sorted, safePage]
  );

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
          placeholder="종목명 검색"
          className="w-56 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-500 focus:outline-none"
        />

        <button
          onClick={() => downloadCsv(filteredRaw, priceDate)}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          CSV 다운로드
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-500">
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  onClick={() => handleSort(column.key)}
                  className={`cursor-pointer select-none whitespace-nowrap px-3 py-3 font-semibold hover:text-gray-800 ${
                    column.align === "right" ? "text-right" : ""
                  }`}
                >
                  {column.label}
                  {sortKey === column.key && <span className="ml-1">{sortDir === "asc" ? "▲" : "▼"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row) => (
              <tr key={`${row.code}-${row.tradable_date}`} className="border-b border-gray-100 last:border-0">
                <td className="whitespace-nowrap px-3 py-3">
                  <Link href={`/stock/${row.code}`} className="font-medium text-blue-600 hover:underline">
                    {row.name}
                  </Link>
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.listing_date}</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.date_display}</td>
                <td className="whitespace-nowrap px-3 py-3 text-right font-medium">{formatEok(row.scale)}</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{row.qty.toLocaleString("ko-KR")}주</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{Math.round(row.pct * 100) / 100}%</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.periods}</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{formatEok(row.marketCap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-gray-500">
        <span>총 {sorted.length}건</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage(safePage - 1)}
            disabled={safePage <= 1}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-white"
          >
            이전
          </button>
          <span className="min-w-14 text-center tabular-nums">
            {safePage} / {totalPages}
          </span>
          <button
            onClick={() => setPage(safePage + 1)}
            disabled={safePage >= totalPages}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-white"
          >
            다음
          </button>
        </div>
      </div>
    </div>
  );
}
