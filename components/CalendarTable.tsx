"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { FlatRow, LockupCategory } from "@/lib/data";

type FilterKey = "전체" | LockupCategory;
type SortKey = "listing_date" | "category" | "period" | "tradable_date" | "qty" | "pct" | "marketCap" | "status";
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

const FILTERS: FilterKey[] = ["전체", "IPO기관", "구주·보호예수"];

function formatPriceDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${y}.${m}.${d}`;
}

function formatEok(won: number): string {
  return `${Math.round(won / 1e8).toLocaleString("ko-KR")}억원`;
}

function buildColumns(priceDate: string, showCategory: boolean): { key: SortKey; label: React.ReactNode; align?: "right" }[] {
  const base: { key: SortKey; label: React.ReactNode; align?: "right" }[] = [
    { key: "listing_date", label: "상장일" },
  ];

  if (showCategory) base.push({ key: "category", label: "구분" });

  return [
    ...base,
    { key: "period", label: "기간" },
    { key: "tradable_date", label: "해제일" },
    { key: "qty", label: "락업 해제 물량", align: "right" },
    {
      key: "pct",
      align: "right",
      label: (
        <>
          비중
          <br />
          <span className="font-normal text-ink-muted">(상장 주식 대비)</span>
        </>
      ),
    },
    {
      key: "marketCap",
      align: "right",
      label: (
        <>
          시가총액
          <br />
          <span className="font-normal text-ink-muted">{formatPriceDate(priceDate)} 종가 기준</span>
        </>
      ),
    },
    { key: "status", label: "상태" },
  ];
}

function compare(a: FlatRow, b: FlatRow, key: SortKey): number {
  switch (key) {
    case "listing_date":
    case "category":
    case "tradable_date":
    case "status":
      return String(a[key] || "").localeCompare(String(b[key] || ""));
    case "period":
      return (PERIOD_ORDER[a.period] ?? 999) - (PERIOD_ORDER[b.period] ?? 999);
    case "qty":
      return a.qty - b.qty;
    case "pct":
      return a.pct - b.pct;
    case "marketCap":
      return a.marketCap - b.marketCap;
  }
}

function statusClass(status: string): string {
  if (status === "예정") return "bg-blue-100 text-blue-700";
  if (status === "반환확인" || status === "반환확인_API수정") return "bg-green-100 text-green-700";
  if (status === "수동확인" || status === "수동/API불일치") return "bg-amber-100 text-amber-700";
  return "bg-cream-deep text-ink-soft";
}

function categoryClass(category: LockupCategory): string {
  return category === "IPO기관" ? "bg-[#eef7d2] text-[#4a6510]" : "bg-cream-deep text-ink-soft";
}

function downloadCsv(rows: FlatRow[], priceDate: string, filter: FilterKey) {
  const headers = [
    "종목",
    "종목코드",
    "시장",
    "상장일",
    "구분",
    "기간",
    "해제일",
    "실제거래가능일",
    "락업 해제 물량",
    "비중(상장 주식 대비)(%)",
    `시가총액(원, ${formatPriceDate(priceDate)} 종가 기준)`,
    "상태",
  ];
  const lines = [
    headers.join(","),
    ...rows.map((r) =>
      [r.name, r.code, r.market, r.listing_date, r.category, r.period, r.date_display, r.tradable_date, r.qty, r.pct, r.marketCap, r.status]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
        .join(",")
    ),
  ];
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const suffix = filter === "전체" ? "전체" : filter;
  a.download = `락업해제일정_${suffix}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function CalendarTable({ rows, priceDate }: { rows: FlatRow[]; priceDate: string }) {
  const [filter, setFilter] = useState<FilterKey>("전체");
  const [sortKey, setSortKey] = useState<SortKey>("tradable_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const showCategory = filter === "전체";
  const columns = useMemo(() => buildColumns(priceDate, showCategory), [priceDate, showCategory]);

  const filtered = useMemo(() => {
    if (filter === "전체") return rows;
    return rows.filter((row) => row.category === filter);
  }, [rows, filter]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => compare(a, b, sortKey) * (sortDir === "asc" ? 1 : -1));
    return copy;
  }, [filtered, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-full border border-hairline bg-card p-1 text-sm">
          {FILTERS.map((item) => (
            <button
              key={item}
              onClick={() => setFilter(item)}
              className={`rounded-full px-4 py-1.5 font-medium transition-colors ${
                filter === item ? "bg-ink text-white" : "text-ink-soft hover:bg-cream hover:text-ink"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <button
          onClick={() => downloadCsv(sorted, priceDate, filter)}
          className="rounded-full border border-hairline bg-card px-4 py-1.5 text-sm font-medium text-ink-soft transition-colors hover:bg-cream-deep hover:text-ink"
        >
          ⬇ 엑셀(CSV) 다운로드
        </button>
      </div>

      <div className="card overflow-hidden rounded-2xl">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="border-b border-hairline bg-cream-deep/60 text-left text-ink-muted">
                <th className="whitespace-nowrap px-4 py-3 font-semibold">종목</th>
                <th className="whitespace-nowrap px-4 py-3 font-semibold">시장</th>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className={`cursor-pointer select-none whitespace-nowrap px-4 py-3 font-semibold hover:text-ink ${col.align === "right" ? "text-right" : ""}`}
                  >
                    {col.label}
                    {sortKey === col.key && <span className="ml-1">{sortDir === "asc" ? "▲" : "▼"}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr
                  key={`${r.code}-${r.category}-${r.period}-${r.tradable_date}-${i}`}
                  className="border-b border-hairline/60 transition-colors last:border-0 hover:bg-cream/50"
                >
                  <td className="whitespace-nowrap px-4 py-3">
                    <Link href={`/stock/${r.code}`} className="font-semibold text-ink hover:underline">{r.name}</Link>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-muted">{r.market}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-muted tabular-nums">{r.listing_date}</td>
                  {showCategory && (
                    <td className="px-4 py-3">
                      <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${categoryClass(r.category)}`}>
                        {r.category}
                      </span>
                    </td>
                  )}
                  <td className="whitespace-nowrap px-4 py-3 text-ink-soft">
                    <div>{r.period}</div>
                    {r.category === "구주·보호예수" && (r.holder_name || r.reason) && (
                      <div className="mt-0.5 max-w-[180px] truncate text-xs text-ink-muted">{r.holder_name || r.reason}</div>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-soft tabular-nums">{r.date_display}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">{r.qty.toLocaleString("ko-KR")}주</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">{r.pct}%</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">{formatEok(r.marketCap)}</td>
                  <td className="px-4 py-3">
                    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(r.status)}`}>{r.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
