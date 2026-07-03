import { ChapterPage } from "@/components/ChapterPage";
import { DualAxisChart } from "@/components/DualAxisChart";
import { fetchOilVsCpi } from "@/lib/oilCpi";

export const revalidate = 86400;

export default async function OilCpiPage() {
  const data = await fetchOilVsCpi().catch(() => null);

  return (
    <ChapterPage
      eyebrow="COMMODITIES"
      title="유가 ↔ 물가(CPI)"
      description="WTI 유가 월평균과 한국 CPI YoY를 실제 관측월 기준으로 비교합니다."
    >
      {data ? (
        <DualAxisChart series={data} />
      ) : (
        <p className="text-ink-muted-48">데이터 로딩 실패</p>
      )}
    </ChapterPage>
  );
}
