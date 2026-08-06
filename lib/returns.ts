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
