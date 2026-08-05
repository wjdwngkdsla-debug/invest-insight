import type { Metadata } from "next";
import { getIpoRanking } from "@/lib/ranking";
import { getSiteData } from "@/lib/data";
import { IpoRankingTable } from "@/components/IpoRankingTable";

export const metadata: Metadata = {
  title: "IPO 랭킹 | IPO 락업 캘린더",
  description:
    "공모가 대비 현재 주가 수익률로 IPO 종목을 순위화합니다. 상장일 기간·시장별로 수요예측 경쟁률, 개인청약 경쟁률, 시가총액을 함께 비교하세요.",
  alternates: { canonical: "/ranking" },
};

export default function IpoRankingPage() {
  const rows = getIpoRanking();
  const { updated } = getSiteData();

  return (
    <main className="mx-auto w-full max-w-[1040px] px-5 py-6">
      <h1 className="sr-only">IPO 랭킹</h1>
      <IpoRankingTable rows={rows} priceDate={updated.slice(5)} />
    </main>
  );
}
