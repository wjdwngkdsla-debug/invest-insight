import type { Metadata } from "next";
import { getLockupRanking } from "@/lib/lockupRanking";
import { LockupRankingTable } from "@/components/LockupRankingTable";

export const metadata: Metadata = {
  title: "락업 랭킹 | IPO 락업 캘린더",
  description:
    "기관 의무보유확약(15일·1개월·3개월·6개월) 물량이 풀린 날, 주가가 전 거래일 대비 얼마나 움직였는지 순위로 봅니다. 확약 기간·시장·해제일 기간별로 비교하세요.",
  alternates: { canonical: "/lockup-ranking" },
};

export default function LockupRankingPage() {
  const rows = getLockupRanking();

  return (
    <main className="mx-auto w-full max-w-[1040px] px-5 py-6">
      <h1 className="sr-only">락업 랭킹</h1>
      <LockupRankingTable rows={rows} />
    </main>
  );
}
