import { ChapterPage } from "@/components/ChapterPage";
import { DualAxisChart } from "@/components/DualAxisChart";
import { fetchSemiconductorVsKospi } from "@/lib/semiKospi";

export const revalidate = 86400;

export default async function SemiconductorKospiPage() {
  const data = await fetchSemiconductorVsKospi().catch(() => null);

  return (
    <ChapterPage
      eyebrow="TRADE"
      title="반도체 수출액 ↔ KOSPI 상관관계"
      description="주요 교역국(미국·중국·일본·베트남·홍콩·대만·EU) 합산 기준 반도체(모노리식 집적회로) 수출액과 KOSPI 지수를 비교합니다."
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
