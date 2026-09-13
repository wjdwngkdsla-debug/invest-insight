import { createHash } from "node:crypto";
import type { TradeDataset } from "./trade";

export type TradeUpdate = { id: string; productId: string; name: string; month: string; checkedAt: string | null; source: string };
export function buildTradeUpdates(datasets: Record<string, TradeDataset | null>, products: readonly { id: string; name: string }[]): TradeUpdate[] {
  return products.flatMap(product => {
    const data = datasets[product.id];
    if (!data) return [];
    const month = [...new Set(data.rows.map(r => r.month))].sort().at(-1);
    if (!month) return [];
    const canonical = [...data.rows].sort((a, b) => a.month.localeCompare(b.month) || a.country.localeCompare(b.country)).map(r => [r.month, r.country, r.usd, r.kg ?? null]);
    const revision = createHash("sha256").update(JSON.stringify({ hs: data.hs, rows: canonical,
      totals: Object.entries(data.monthlyTotals ?? {}).sort(), weights: Object.entries(data.monthlyWeightTotals ?? {}).sort() })).digest("hex").slice(0, 16);
    return [{ id: `${product.id}:${month}:${revision}`, productId: product.id, name: product.name, month, checkedAt: data.retrievedAt ?? null, source: data.source }];
  });
}
