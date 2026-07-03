import { ChapterPage } from "@/components/ChapterPage";
import { FxExportChart } from "@/components/FxExportChart";
import { fetchFxVsExport } from "@/lib/fxExport";

export const revalidate = 86400;

export default async function FxExportPage() {
  const data = await fetchFxVsExport().catch(() => null);

  return (
    <ChapterPage
      eyebrow="FX"
      title="전체 수출액 ↔ 주요 통화 환율"
      description="원/달러·원/엔·원/유로·원/위안 환율과 전체 수출액(억 달러)을 함께 봅니다."
    >
      {data ? (
        <FxExportChart series={data} />
      ) : (
        <p className="text-ink-muted-48">데이터 로딩 실패</p>
      )}
    </ChapterPage>
  );
}
