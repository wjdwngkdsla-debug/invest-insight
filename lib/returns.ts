import type { StockLockup } from "@/lib/types";

/** 기준가 대비 수익률. 가격이 없으면 계산하지 않는다. */
export function priceReturnPct(basePrice: number, currentPrice: number): number | null {
  if (!basePrice || !currentPrice) return null;
  return ((currentPrice - basePrice) / basePrice) * 100;
}

/**
 * 현재 공모가 대비 수익률의 단일 기준.
 * 거래정지 중인 종목의 종가는 과거 마지막 체결가이므로 현재 수익률로 취급하지 않는다.
 */
export function currentIpoReturnPct(
  stock: Pick<StockLockup, "ipo_price" | "adjusted_ipo_price" | "close_price" | "trading_suspended">,
): number | null {
  if (stock.trading_suspended) return null;
  return priceReturnPct(stock.adjusted_ipo_price || stock.ipo_price || 0, stock.close_price || 0);
}

/** 상장 시점 주식수. KRX 상장일 스냅샷(LIST_SHRS)이 원천이고, 없으면 편입 시점 값으로 대체한다. */
export function listingShares(stock: Pick<StockLockup, "initial_shares" | "shares">): number {
  return stock.initial_shares || stock.shares || 0;
}

/**
 * 상장일 유통가능비율 — 상장 당일 매도 제한이 없던 주식의 비중.
 *
 * 분모는 상장일 상장주식수, 분자에서 빼는 물량은 기존주주 보호예수와 기관 의무보유확약
 * 전부다. 확약은 최소 15일이라 상장 당일에는 팔 수 없으므로 유통물량이 아니다.
 * (투자설명서의 '유통가능물량'은 확약분을 포함해 계산하므로 이 값보다 크게 나온다.)
 *
 * 투자설명서 유통가능 요약표에서 보호예수를 받은 종목만 계산한다. 공공데이터 API는
 * '반환 실적'이라 아직 안 풀린 장기 보호예수가 통째로 빠지고, 그러면 유통물량이
 * 실제보다 훨씬 크게 나온다(이뮨온시아: 3년 보호예수 4,889만주 누락 → 92.6%로 표시).
 */
export function listingFloatPct(
  stock: Pick<StockLockup, "initial_shares" | "shares" | "events">,
): number | null {
  const events = stock.events || [];
  const fromProspectus = events.some(
    (event) => event.type === "보호예수" && (event.source_label || "").includes("투자설명서"),
  );
  if (!fromProspectus) return null;
  const base = listingShares(stock);
  const locked = events.reduce((sum, event) => sum + (event.qty || 0), 0);
  if (!base || !locked || locked > base) return null;
  return ((base - locked) / base) * 100;
}

/** 상장일 시가총액 — 상장일 상장주식수 × 상장일 종가. */
export function listingMarketCap(
  stock: Pick<StockLockup, "initial_shares" | "shares" | "listing_close">,
): number | null {
  const base = listingShares(stock);
  if (!base || !stock.listing_close) return null;
  return base * stock.listing_close;
}
