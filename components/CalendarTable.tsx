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
      return String(a[key] || "").localeCompare(String(b[key] || ""), "ko-KR");
    case "status": {
      // 화면에 보이는 상태(예정/해제완료) 기준으로 정렬하고, 같은 상태끼리는 해제일순
      const s = displayStatus(a.tradable_date).localeCompare(displayStatus(b.tradable_date), "ko-KR");
      return s !== 0 ? s : a.tradable_date.localeCompare(b.tradable_date);
    }
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

const PAGE_SIZE = 20;

export function CalendarTable({ rows }: { rows: FlatRow[]; priceDate?: string }) {
  const [filter, setFilter] = useState<FilterKey>("전체");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("tradable_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim();
    let out = filter === "전체" ? rows : rows.filter((row) => row.category === filter);
    if (q) out = out.filter((row) => row.name.includes(q));
    return out;
  }, [rows, filter, query]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => compare(a, b, sortKey) * (sortDir === "asc" ? 1 : -1));
    return copy;
  }, [filtered, sortKey, sortDir]);

  // 페이지 자르기는 필터·정렬이 모두 끝난 결과에 마지막으로 적용 — 정렬/필터와 충돌하지 않는다
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
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
            {FILTERS.map((item) => (
              <button
                key={item}
                onClick={() => {
                  setFilter(item);
                  setPage(1);
                }}
                className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
                  filter === item ? "bg-gray-900 text-white" : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="종목명 검색"
            className="w-40 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
          />
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
            {paged.map((row, index) => (
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
