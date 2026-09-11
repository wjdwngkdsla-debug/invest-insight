import type { Metadata } from "next";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { TradeDashboard } from "@/components/trade/TradeDashboard";
import { tradeProducts, validTradeDataset, type TradeDataset } from "@/lib/trade";

export const metadata: Metadata = {
  title: "수출 동향 | D램·화장품 국가별 수출금액과 중량",
  description: "관세청 통계로 확인하는 D램·화장품 월별 수출금액, 순중량, kg당 수출액 및 국가별 수출 지도.",
  alternates: { canonical: "https://vericap.co.kr/trade" },
};
export const dynamic = "force-static";

export default async function TradePage() {
  const datasets: Record<string, TradeDataset | null> = {};
  for (const product of tradeProducts) {
    datasets[product.id] = null;
    try {
      const cached: unknown = JSON.parse(await readFile(join(process.cwd(), `data/trade/${product.id}.json`), "utf8"));
      if (validTradeDataset(cached, product.hs)) datasets[product.id] = cached;
    } catch { /* Missing/invalid observations stay missing, never synthetic. */ }
  }
  return <TradeDashboard datasets={datasets} />;
}
