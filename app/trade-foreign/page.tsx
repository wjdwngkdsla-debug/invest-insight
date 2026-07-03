import { ChapterPage } from "@/components/ChapterPage";
import { DualAxisChart } from "@/components/DualAxisChart";
import { fetchTradeBalanceVsForeign } from "@/lib/tradeForeign";

export const revalidate = 86400;

export default async function TradeForeignPage() {
  const data = await fetchTradeBalanceVsForeign().catch(() => null);

  return (
    <ChapterPage
      eyebrow="FLOWS"
      title="무역수지 ↔ 외국인 순매수"
      description="월별 무역수지(억 달러)와 코스피 외국인 순매수(억원)를 비교합니다."
      tone="dark"
    >
      {data ? (
        <DualAxisChart series={data} />
      ) : (
        <p className="text-body-muted">데이터 로딩 실패</p>
      )}
    </ChapterPage>
  );
}
