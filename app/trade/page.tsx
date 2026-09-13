import type { Metadata } from "next";
import { TradeDashboard } from "@/components/trade/TradeDashboard";
import { loadTradeCompanies, loadTradeDatasets } from "@/lib/trade-server";

export const metadata: Metadata = {
  title: "수출 동향 | D램·화장품·변압기 국가별 수출금액과 중량",
  description: "관세청 통계로 확인하는 D램·화장품·대형 변압기 기간별 수출금액, 순중량, kg당 수출액 및 국가별 수출 지도.",
  alternates: { canonical: "https://vericap.co.kr/trade" },
};
export const dynamic = "force-static";

export default async function TradePage() {
  const datasets = await loadTradeDatasets();
  const companies = await loadTradeCompanies();
  return <TradeDashboard datasets={datasets} companies={companies} />;
}
