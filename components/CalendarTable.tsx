"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { displayStatus, type FlatRow, type LockupCategory } from "@/lib/data";

type FilterKey = "전체" | LockupCategory;
type SortKey =
  | "name"
  | "market"
  | "listing_date"
  | "category"
  | "period"
  | "tradable_date"
  | "qty"
  | "pct"
  | "marketCap"
  | "status";
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

const FILTERS: FilterKey[] = ["전체", "IPO기관", "기존주주"];

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "name", label: "종목" },
  { key: "market", label: "시장" },
  { key: "listing_date", label: "상장일" },
  { key: "category", label: "구분" },
  { key: "period", label: "기간" },
  { key: "tradable_date", label: "해제일" },
  { key: "qty", label: "락업 해제 물량", align: "right" },
  { key: "pct", label: "비중", align: "right" },
  { key: "marketCap", label: "시가총액", align: "right" },
  { key: "status", label: "상태" },
];

function formatEok(won: number): string {
  return `${Math.round(won / 1e8).toLocaleString("ko-KR")}억원`;
}

function compare(a: FlatRow, b: FlatRow, key: SortKey): number {
  switch (key) {
    case "name":
      return a.name.localeCompare(b.name, "ko-KR");
    case "market":
    case "listing_date":
    case "category":
    case "tradable_date":
    case "status":
      return String(a[key] || "").localeCompare(String(b[key] || ""), "ko-KR");
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
  return status === "예정" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600";
}

function downloadCsv(rows: FlatRow[], filter: FilterKey) {
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
    "비중(상장 주식 대비 %)",
    "시가총액",
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
        r.tradable_date,
        r.qty,
        r.pct,
        r.marketCap,
        displayStatus(r.tradable_date),
      ]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
        .join(",")
    ),
  ];
  const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `락업해제일정_${filter}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function CalendarTable({ rows }: { rows: FlatRow[]; priceDate?: string }) {
  const [filter, setFilter] = useState<FilterKey>("전체");
  const [sortKey, setSortKey] = useState<SortKey>("tradable_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

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
    if (key === sortKey) setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
          {FILTERS.map((item) => (
            <button
              key={item}
              onClick={() => setFilter(item)}
              className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
                filter === item ? "bg-gray-900 text-white" : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <button
          onClick={() => downloadCsv(sorted, filter)}
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
            {sorted.map((row, index) => (
              <tr key={`${row.code}-${row.category}-${row.period}-${row.tradable_date}-${index}`} className="border-b border-gray-100 last:border-0">
                <td className="whitespace-nowrap px-3 py-3">
                  <Link href={`/stock/${row.code}`} className="font-medium text-blue-600 hover:underline">
                    {row.name}
                  </Link>
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.market}</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.listing_date}</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-700">{row.category}</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.period}</td>
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{row.date_display}</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{row.qty.toLocaleString("ko-KR")}주</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{row.pct}%</td>
                <td className="whitespace-nowrap px-3 py-3 text-right">{formatEok(row.marketCap)}</td>
                <td className="whitespace-nowrap px-3 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(displayStatus(row.tradable_date))}`}>
                    {displayStatus(row.tradable_date)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
