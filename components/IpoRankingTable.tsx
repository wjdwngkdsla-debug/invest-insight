"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { IpoRankingRow } from "@/lib/ranking";
import { formatKrwEok } from "@/lib/format";

type MarketKey = "all" | "코스피" | "코스닥";
type OutcomeKey = "all" | "win" | "loss";
type SortKey = "marketCap" | "returnPct" | "listingReturnPct" | "demandRatio" | "subRatio" | "listingDate";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "marketCap", label: "시가총액" },
  { key: "returnPct", label: "공모가 대비" },
  { key: "listingReturnPct", label: "상장일 수익률" },
  { key: "demandRatio", label: "수요예측" },
  { key: "subRatio", label: "개인청약" },
  { key: "listingDate", label: "상장일" },
];

function ratioText(value: number): string {
  if (!value) return "-";
  const digits = value >= 100 ? 0 : 2;
  return `${value.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}:1`;
}

function yymmdd(date: string): string {
  return date ? date.slice(2).replaceAll("-", ".") : "-";
}

function ReturnText({ pct, suspended = false, className = "" }: { pct: number | null; suspended?: boolean; className?: string }) {
  if (suspended) return <span className={`font-semibold text-slate-500 ${className}`}>거래정지</span>;
  if (pct === null) return <span className="text-slate-300">-</span>;
  const up = pct >= 0;
  return (
    <span className={`font-bold tabular-nums ${up ? "text-rose-600" : "text-blue-600"} ${className}`}>
      {up ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

const CHIP_BASE = "rounded-full px-3 py-1 text-[12px] font-semibold transition-colors";
const CHIP_ON = "bg-blue-600 text-white";
const CHIP_OFF = "border border-gray-200 bg-white text-slate-600 hover:bg-gray-50";
const DATE_INPUT =
  "rounded-lg border border-gray-200 bg-white px-2 py-1 text-[12px] font-medium text-slate-700 focus:border-blue-400 focus:outline-none";

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

export function IpoRankingTable({ rows, priceDate }: { rows: IpoRankingRow[]; priceDate: string }) {
  // 캘린더 선택 범위는 실제 보유 데이터의 상장일 구간으로 제한한다.
  const bounds = useMemo(() => {
    const dates = rows.map((row) => row.listingDate).filter(Boolean).sort();
    return { min: dates[0] || "", max: dates[dates.length - 1] || "" };
  }, [rows]);

  const [market, setMarket] = useState<MarketKey>("all");
  const [outcome, setOutcome] = useState<OutcomeKey>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("returnPct");
  const [asc, setAsc] = useState(false);

  const filtered = useMemo(
    () =>
      rows.filter((row) => {
        if (market !== "all" && row.market !== market) return false;
        if (outcome === "win" && (row.returnPct === null || row.returnPct < 0)) return false;
        if (outcome === "loss" && (row.returnPct === null || row.returnPct >= 0)) return false;
        if (from && row.listingDate < from) return false;
        if (to && row.listingDate > to) return false;
        return true;
      }),
    [rows, market, outcome, from, to],
  );

  const sorted = useMemo(() => {
    const list = [...filtered].sort((a, b) => {
      if (sortKey === "listingDate") {
        const diff = a.listingDate.localeCompare(b.listingDate);
        return asc ? diff : -diff;
      }
      if (sortKey === "listingReturnPct" || sortKey === "returnPct") {
        const av = a[sortKey];
        const bv = b[sortKey];
        // 시세 미확인·거래정지는 정렬 방향과 무관하게 뒤로 보낸다.
        if (av === null && bv === null) return 0;
        if (av === null) return 1;
        if (bv === null) return -1;
        return asc ? av - bv : bv - av;
      }
      const diff = a[sortKey] - b[sortKey];
      return asc ? diff : -diff;
    });
    return list;
  }, [filtered, sortKey, asc]);

  const summary = useMemo(() => {
    if (filtered.length === 0) return null;
    const comparable = filtered.filter((row) => row.returnPct !== null);
    const total = comparable.reduce((sum, row) => sum + (row.returnPct ?? 0), 0);
    const listed = filtered.filter((row) => row.listingReturnPct !== null);
    const listedTotal = listed.reduce((sum, row) => sum + (row.listingReturnPct ?? 0), 0);
    return {
      count: filtered.length,
      average: comparable.length ? total / comparable.length : null,
      listingAverage: listed.length ? listedTotal / listed.length : null,
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
      {/* 필터 한 줄 — 시장 · 성과 · 상장일 기간(캘린더) */}
      <div className="rounded-[20px] border border-gray-200 bg-white p-3.5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {(["all", "코스피", "코스닥"] as MarketKey[]).map((key) => (
            <button key={key} type="button" onClick={() => setMarket(key)} className={`${CHIP_BASE} ${market === key ? CHIP_ON : CHIP_OFF}`}>
              {key === "all" ? "전체" : key}
            </button>
          ))}
          <span aria-hidden className="mx-1 hidden h-4 w-px bg-gray-200 sm:block" />
          {([
            { key: "all", label: "전체" },
            { key: "win", label: "공모가 이상" },
            { key: "loss", label: "공모가 미만" },
          ] as { key: OutcomeKey; label: string }[]).map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setOutcome(option.key)}
              className={`${CHIP_BASE} ${outcome === option.key ? CHIP_ON : CHIP_OFF}`}
            >
              {option.label}
            </button>
          ))}
          <span aria-hidden className="mx-1 hidden h-4 w-px bg-gray-200 sm:block" />
          <span className="text-[11.5px] font-semibold text-slate-400">상장일</span>
          <input
            type="date"
            value={from}
            min={bounds.min}
            max={to || bounds.max}
            onChange={(event) => setFrom(event.target.value)}
            className={DATE_INPUT}
            aria-label="상장일 시작"
          />
          <span className="text-[12px] text-slate-400">~</span>
          <input
            type="date"
            value={to}
            min={from || bounds.min}
            max={bounds.max}
            onChange={(event) => setTo(event.target.value)}
            className={DATE_INPUT}
            aria-label="상장일 종료"
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
        </div>
      </div>

      {/* 요약 — 필터 구간의 공모 성적표 */}
      {summary && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">대상 종목</p>
            <p className="mt-0.5 text-[17px] font-bold tabular-nums text-slate-900">{summary.count}개</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">현재 평균 수익률</p>
            <p className="mt-0.5 flex items-baseline gap-1 text-[17px]">
              <ReturnText pct={summary.average} />
              <span className="text-[10.5px] font-medium text-slate-400">{priceDate} 기준</span>
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5">
            <p className="text-[11px] font-medium text-slate-500">상장일 평균 수익률</p>
            <p className="mt-0.5 flex items-baseline gap-1 text-[17px]">
              <ReturnText pct={summary.listingAverage} />
              <span className="text-[10.5px] font-medium text-slate-400">상장 첫날</span>
            </p>
          </div>
        </div>
      )}

      {sorted.length === 0 ? (
        <p className="rounded-[20px] border border-gray-200 bg-white p-6 text-sm text-gray-400">
          선택한 조건에 해당하는 종목이 없습니다.
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
                  <tr key={row.code} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60">
                    <td className="px-3 py-2.5">
                      <RankBadge rank={index + 1} />
                    </td>
                    <td className="px-3 py-2.5">
                      <Link href={`/stock/${row.code}`} className="font-semibold text-slate-900 underline-offset-4 hover:text-blue-700 hover:underline">
                        {row.name}
                      </Link>
                      {row.suspended && (
                        <span className="ml-1.5 rounded bg-gray-200/80 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">거래정지</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{formatKrwEok(row.marketCap)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <ReturnText pct={row.returnPct} suspended={row.suspended} />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <ReturnText pct={row.listingReturnPct} />
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{ratioText(row.demandRatio)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">{ratioText(row.subRatio)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">{yymmdd(row.listingDate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 모바일: 카드 목록 */}
          <ul className="space-y-2.5 md:hidden">
            {sorted.map((row, index) => (
              <li key={row.code} className="rounded-[18px] border border-gray-200 bg-white p-3.5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <RankBadge rank={index + 1} />
                    <Link href={`/stock/${row.code}`} className="truncate font-bold text-slate-900">
                      {row.name}
                    </Link>
                  </div>
                  <ReturnText pct={row.returnPct} suspended={row.suspended} className="shrink-0 text-[17px]" />
                </div>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 rounded-xl border border-gray-200 bg-gray-50/80 px-3 py-2 text-[11px]">
                  <span className="text-slate-500">
                    시총 <span className="font-semibold tabular-nums text-slate-700">{formatKrwEok(row.marketCap)}</span>
                  </span>
                  <span className="text-slate-500">
                    상장일 수익률 <ReturnText pct={row.listingReturnPct} className="text-[11px]" />
                  </span>
                  <span className="text-slate-500">
                    수요예측 <span className="font-semibold tabular-nums text-slate-700">{ratioText(row.demandRatio)}</span>
                  </span>
                  <span className="text-slate-500">
                    개인청약 <span className="font-semibold tabular-nums text-slate-700">{ratioText(row.subRatio)}</span>
                  </span>
                  <span className="text-slate-500">
                    상장 <span className="font-semibold tabular-nums text-slate-700">{yymmdd(row.listingDate)}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="px-1 text-[11px] leading-relaxed text-slate-400">
        <span className="font-semibold text-slate-500">공모가 대비</span>는 공모주를 받아 지금까지 보유했을 때,{" "}
        <span className="font-semibold text-slate-500">상장일 수익률</span>은 상장 첫날 종가에 팔았을 때의 수익률입니다.
        <br />
        무상증자·액면분할처럼 주식수가 바뀐 종목은 토스 수정주가 기준으로 공모가를 보정해 실제 수익률에 맞춥니다.
        거래정지 종목은 마지막 체결가가 현재가처럼 보이지 않도록 수익률과 평균에서 제외합니다.
      </p>
    </div>
  );
}
