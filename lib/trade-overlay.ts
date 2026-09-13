export type OverlayMetric = "none" | "price" | "revenue" | "operatingProfit";
export type CompanyHistory = {
  id: string; name: string; ticker: string; products: string[];
  prices: { month: string; date: string; close: number }[];
  quarters: { month: string; period: string; revenue: number | null; operatingProfit: number | null; basis: "CFS"; receipt: string; filedAt: string | null }[];
  errors?: string[];
};
export type OverlayDataset = { version: number; priceSource: string; financialSource: string; priceBasis: string; pricePublicUse: string; companies: CompanyHistory[] };
export const overlayMetricNames: Record<OverlayMetric, string> = { none: "비교 안 함", price: "주가", revenue: "분기 매출", operatingProfit: "분기 영업이익" };
export function overlayPoints(company: CompanyHistory, metric: OverlayMetric, months: string[]) {
  return months.map(month => {
    if (metric === "none") return { month, value: null, label: "", filedAt: null };
    if (metric === "price") {
      const point = company.prices.find(p => p.month === month);
      return { month, value: point?.close ?? null, label: point?.date ?? "", filedAt: null };
    }
    const point = company.quarters.find(p => p.month === month);
    const amount = point?.[metric];
    return { month, value: amount === null || amount === undefined ? null : amount / 1e8, label: point?.period ?? "", filedAt: point?.filedAt ?? null };
  });
}
export function validOverlayDataset(value: unknown): value is OverlayDataset {
  const data = value as OverlayDataset | null;
  return !!data && data.version === 1 && Array.isArray(data.companies) && data.companies.every(c =>
    typeof c.id === "string" && typeof c.name === "string" && /^\d{6}$/.test(c.ticker) && Array.isArray(c.products) &&
    Array.isArray(c.prices) && Array.isArray(c.quarters) &&
    new Set(c.prices.map(p => p.month)).size === c.prices.length && new Set(c.quarters.map(p => p.month)).size === c.quarters.length &&
    c.prices.every(p => /^\d{4}-\d{2}$/.test(p.month) && p.date?.startsWith(p.month) && Number.isFinite(p.close) && p.close > 0) &&
    c.quarters.every(p => /^\d{4}-(03|06|09|12)$/.test(p.month) && p.basis === "CFS" && [p.revenue, p.operatingProfit].every(n => n === null || Number.isFinite(n))));
}
