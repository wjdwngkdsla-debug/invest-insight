import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { tradeProducts, validTradeDataset, type TradeDataset } from "./trade";
import { validOverlayDataset, type CompanyHistory } from "./trade-overlay";

export async function loadTradeDatasets() {
  const datasets: Record<string, TradeDataset | null> = {};
  for (const product of tradeProducts) {
    datasets[product.id] = null;
    try {
      const data: unknown = JSON.parse(await readFile(join(process.cwd(), `data/trade/${product.id}.json`), "utf8"));
      if (validTradeDataset(data, product.hs)) datasets[product.id] = data;
    } catch { /* Missing or invalid cache stays unavailable. */ }
  }
  return datasets;
}
export async function loadTradeCompanies(): Promise<CompanyHistory[]> {
  try {
    const data: unknown = JSON.parse(await readFile(join(process.cwd(), "data/trade/company-history.json"), "utf8"));
    if (!validOverlayDataset(data)) return [];
    const allowPrices = process.env.NODE_ENV === "development" || process.env.TRADE_PRICE_PUBLIC_ENABLED === "true";
    return data.companies.map(c => ({ ...c, prices: allowPrices ? c.prices : [] }));
  } catch { return []; }
}
