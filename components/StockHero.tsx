"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo } from "react";
import type { StockLockup } from "@/lib/types";
import { StockLockupTiles } from "@/components/StockLockupTiles";
import { formatKrwEok } from "@/lib/format";
import { listingFloatPct, listingShares, priceReturnPct } from "@/lib/returns";

const DEFAULT_BLOG_URL = "https://blog.naver.com/vericap";

function ReturnGauge({ pct }: { pct: number }) {
  const clamped = Math.max(-100, Math.min(100, pct));
  const angle = ((90 - (clamped / 100) * 90) * Math.PI) / 180;
  const cx = 100;
  const cy = 91;
  const radius = 66;
  const edge = {
    x: cx + radius * Math.cos(angle),
    y: cy - radius * Math.sin(angle),
  };
  const tip = {
    x: cx + (radius - 12) * Math.cos(angle),
    y: cy - (radius - 12) * Math.sin(angle),
  };
  const up = pct >= 0;

  return (
    <svg viewBox="0 0 200 100" className="h-[68px] w-[136px] md:h-[74px] md:w-[148px]" aria-hidden>
      <path
        d={`M ${cx - radius},${cy} A ${radius},${radius} 0 0 1 ${cx + radius},${cy}`}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d={`M ${cx},${cy - radius} A ${radius},${radius} 0 0 ${up ? 1 : 0} ${edge.x},${edge.y}`}
        fill="none"
        stroke={up ? "#e11d48" : "#2563eb"}
        strokeWidth="8"
        strokeLinecap="round"
      />
      <line x1={cx} y1={cy} x2={tip.x} y2={tip.y} stroke="#334155" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="5" fill="#334155" />
      <circle cx={cx} cy={cy} r="1.8" fill="#ffffff" />
    </svg>
  );
}

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "h-4 w-4",
};

/** 유리 카드 — 배경 그라디언트가 비쳐 보이도록 반투명 + 블러 */
function GlassTile({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50/80 px-3 py-2.5 md:h-[88px] md:px-4 md:py-3">
      <div className="flex items-center gap-1.5 md:gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-gray-200 bg-white text-slate-500">
          {icon}
        </span>
        <p className="whitespace-nowrap text-[10.5px] font-medium leading-tight text-slate-500 md:text-[11.5px]">{label}</p>
      </div>
      <p className="mt-1.5 whitespace-nowrap text-[15px] font-bold leading-tight tracking-tight text-slate-900 md:text-[18px]">{value}</p>
      {sub && <p className="mt-0.5 whitespace-nowrap text-[9.5px] leading-3 text-slate-400 md:text-[10.5px]">{sub}</p>}
    </div>
  );
}

export function StockHero({
  stock,
  updated,
  initialNow,
  adjustedMode = false,
  onAdjustedModeChange,
  quantityFactor = 1,
  displayShares,
}: {
  stock: StockLockup;
  updated: string;
  initialNow: number;
  adjustedMode?: boolean;
  onAdjustedModeChange?: (value: boolean) => void;
  quantityFactor?: number;
  displayShares?: number;
}) {
  const hasAdjustment = Boolean(
    stock.adjustment_events?.length
    && stock.ipo_adjustment_factor
    && Math.abs((stock.ipo_adjustment_factor || 1) - 1) >= 0.001,
  );
  const baseShares = listingShares(stock);
  const activeShares = displayShares || Math.round(baseShares * quantityFactor);
  const ipoPrice = adjustedMode && stock.adjusted_ipo_price ? stock.adjusted_ipo_price : stock.ipo_price || 0;
  const displayEvents = useMemo(() => {
    if (Math.abs(quantityFactor - 1) < 0.001) return stock.events;
    return stock.events.map((event) => ({
      ...event,
      qty: event.unit === "DR" ? event.qty : Math.round(event.qty * quantityFactor),
    }));
  }, [quantityFactor, stock.events]);
  const displayStock = useMemo(() => ({
    ...stock,
    ipo_price: ipoPrice,
    adjusted_ipo_price: 0,
    shares: activeShares,
    initial_shares: activeShares,
    listing_float_shares: stock.listing_float_shares
      ? Math.round(stock.listing_float_shares * quantityFactor)
      : stock.listing_float_shares,
    events: displayEvents,
  }), [activeShares, displayEvents, ipoPrice, quantityFactor, stock]);
  const closeCap = stock.market_cap || stock.shares * stock.close_price;
  const changePct = stock.trading_suspended ? null : priceReturnPct(ipoPrice, stock.close_price || 0);
  const hasReturn = changePct !== null;
  const displayChangePct = changePct ?? 0;
  const up = displayChangePct >= 0;
  const contentUrl = stock.content_url || DEFAULT_BLOG_URL;
  const contentLabel = stock.content_url ? "종목 분석 보러가기" : "기업 분석 포스팅 보러가기";
  const priceDate = updated.slice(5);
  const suspended = stock.trading_suspended === true;
  const suspendedSince = stock.trading_suspended_since || "";
  const offerCap = activeShares && ipoPrice ? activeShares * ipoPrice : null;
  const floatPct = listingFloatPct(displayStock);
  const adjustmentFactor = stock.ipo_adjustment_factor || 1;
  const adjustmentMultiple = adjustmentFactor ? 1 / adjustmentFactor : 1;

  // 핵심 지표 4개를 데스크톱 2×2, 모바일 2열 패널로 그린다.
  const metrics: { label: string; value: string; sub?: string; mobileSub?: string; icon: ReactNode }[] = [
    {
      label: "상장일",
      value: stock.listing_date ? stock.listing_date.slice(2) : "미정",
      icon: <svg {...iconProps}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></svg>,
    },
    {
      label: adjustedMode ? "조정 공모가" : "공모가",
      value: ipoPrice ? `${ipoPrice.toLocaleString("ko-KR")}원` : "미확인",
      icon: <svg {...iconProps}><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9.5 9.8h5M9.5 14.2h5" /></svg>,
    },
    {
      label: suspended ? "거래정지 전 종가" : `최근 종가(${priceDate})`,
      value: stock.close_price ? `${stock.close_price.toLocaleString("ko-KR")}원` : "-",
      icon: <svg {...iconProps}><path d="M3 16.5 9 10l4 4 7.5-7.5M15 6.5h5.5V12" /></svg>,
    },
    {
      // 상장 당일 매도 제한이 없던 물량 비중 — 보호예수·기관확약을 모두 뺀 값
      label: "상장일 유통가능",
      value: floatPct === null ? "-" : `${floatPct.toFixed(1)}%`,
      icon: <svg {...iconProps}><circle cx="12" cy="12" r="9" /><path d="M12 3v9l6.4 3.7" /></svg>,
    },
    {
      label: adjustedMode ? "조정 공모가 시총" : "시가총액(공모가 기준)",
      value: offerCap ? formatKrwEok(offerCap) : "-",
      icon: <svg {...iconProps}><path d="M4 20h16M7 20V9m5 11V4m5 16v-7" /></svg>,
    },
    {
      label: suspended ? "거래정지 전 시가총액" : `시가총액(${priceDate})`,
      value: closeCap ? formatKrwEok(closeCap) : "-",
      icon: <svg {...iconProps}><path d="M20.5 7.5v9l-8.5 4.5-8.5-4.5v-9L12 3z" /><path d="m3.8 7.4 8.2 4.4 8.2-4.4M12 21v-9.2" /></svg>,
    },
  ];

  return (
    <div className="overflow-hidden rounded-[24px] border border-gray-200 bg-white px-4 py-5 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)] md:rounded-[26px] md:px-6 md:py-5">
      <div className="grid gap-5 md:grid-cols-[minmax(0,350px)_1fr] md:gap-5">
        <div className="flex flex-col justify-center gap-4 md:py-2">
          <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-900 md:mt-1 md:text-[28px]">{stock.name}</h1>

          <div className="flex min-w-0 items-center justify-between gap-2">
            <div>
              {suspended ? (
                <div>
                  <p className="text-[30px] font-bold leading-none tracking-tight text-slate-700 md:text-[34px]">거래정지</p>
                  <p className="mt-2 text-[12px] font-medium text-slate-500 md:text-[13px]">
                    {suspendedSince ? `${suspendedSince}부터` : "거래정지 시작일 확인 중"}
                  </p>
                </div>
              ) : hasReturn ? (
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="text-[18px] font-semibold tracking-tight text-slate-600 md:text-[20px]">공모가 대비</span>
                  <span className={`text-[30px] font-bold leading-none tracking-tight md:text-[34px] ${up ? "text-rose-600" : "text-blue-600"}`}>
                    {up ? "+" : ""}
                    {displayChangePct.toFixed(1)}
                    <span className="text-[20px] md:text-[22px]">%</span>
                  </span>
                </div>
              ) : (
                <div className="flex items-baseline gap-2">
                  <span className="text-[18px] font-semibold tracking-tight text-slate-600 md:text-[20px]">공모가 대비</span>
                  <span className="text-[26px] font-bold leading-none text-slate-400">미확인</span>
                </div>
              )}
            </div>
            {!suspended && hasReturn && <ReturnGauge pct={displayChangePct} />}
          </div>

          {/* 락업 물량은 상장 시점 기준으로 공시된 값이라 상장일 상장주식수로 나눠야
              맞다. 현재 주식수로 나누면 무상증자 종목의 비중이 배수만큼 줄어들고,
              잔여+해제+상장일 유통가능이 100%가 되지 않는다(지투지바이오). */}
          <StockLockupTiles
            events={displayEvents}
            shares={activeShares}
            initialNow={initialNow}
          />
        </div>

        {/* 모바일: 카드 6장을 쌓으면 첫 화면을 다 먹는다 → 2열 컴팩트 패널로 압축 */}
        <div className="md:hidden">
          <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 rounded-2xl border border-gray-200 bg-gray-50/80 px-4 py-3.5">
            {metrics.map((metric) => (
              <div key={metric.label} className="min-w-0">
                <p className="break-keep text-[10px] font-medium leading-tight text-slate-500">{metric.label}</p>
                <p className="mt-0.5 break-keep text-[13.5px] font-bold leading-tight text-slate-900">{metric.value}</p>
                {metric.mobileSub && (
                  <p className="text-[9.5px] leading-[12px] text-slate-400">{metric.mobileSub}</p>
                )}
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="shrink-0 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700">
              {stock.market}
            </span>
            <Link
              href={contentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-[13px] font-bold text-white transition-colors hover:bg-blue-700"
            >
              {contentLabel}
            </Link>
          </div>
          {hasAdjustment && onAdjustedModeChange && (
            <button
              type="button"
              onClick={() => onAdjustedModeChange(!adjustedMode)}
              className={`mt-2 w-full rounded-2xl border px-4 py-3 text-[13px] font-bold transition-colors ${
                adjustedMode
                  ? "border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
                  : "border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-100"
              }`}
            >
              {adjustedMode ? "상장 당시 기준" : "주식수 조정 반영"}
            </button>
          )}
          {hasAdjustment && (
            <p className="mt-2 text-center text-[11px] font-medium text-slate-400">
              {adjustedMode ? "조정 후 기준" : "공모 당시 기준"} · 주식수 {adjustmentMultiple.toFixed(2)}배 변동
            </p>
          )}
        </div>

        {/* 데스크톱: CTA는 작은 버튼으로 낮추고, 지표는 핵심 3개 + 시총 2개의 3/2 구조로 정리한다. */}
        <div className="hidden flex-col justify-center gap-3 md:flex">
          <div className="flex items-center gap-2 self-end">
            {hasAdjustment && onAdjustedModeChange && (
              <button
                type="button"
                onClick={() => onAdjustedModeChange(!adjustedMode)}
                className={`h-8 rounded-full border px-3.5 text-[11.5px] font-semibold transition-colors ${
                  adjustedMode
                    ? "border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
                    : "border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-100"
                }`}
              >
                {adjustedMode ? "상장 당시 기준" : "주식수 조정 반영"}
              </button>
            )}
            <span className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700">
              {stock.market}
            </span>
            <Link
              href={contentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex h-8 items-center gap-1.5 rounded-full bg-blue-600 px-3.5 text-[11.5px] font-semibold text-white transition-colors hover:bg-blue-700"
            >
              {contentLabel}
            </Link>
          </div>
          {/* 타일이 6개로 늘어 3열 2행으로 배치한다. 2열이면 3행이 되어 왼쪽 열보다 높아진다. */}
          <div className="grid grid-cols-3 gap-2.5">
            {metrics.map((metric) => (
              <div key={metric.label}>
                <GlassTile label={metric.label} value={metric.value} sub={metric.sub} icon={metric.icon} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
