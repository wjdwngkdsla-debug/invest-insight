import { ChapterPage } from "@/components/ChapterPage";
import { CountryIndicatorCard } from "@/components/CountryIndicatorCard";
import { fetchAllBaseRates } from "@/lib/rates";

export const revalidate = 86400;

export default async function RatesPage() {
  const rates = await fetchAllBaseRates().catch(() => null);

  return (
    <ChapterPage
      eyebrow="RATES"
      title="기준금리 (국가별)"
      description="한국·미국·일본·유럽·중국 5개국 기준금리를 분기별로 비교합니다."
      tone="parchment"
    >
      {rates ? (
        <CountryIndicatorCard unit="%" countries={rates} />
      ) : (
        <p className="text-ink-muted-48">데이터 로딩 실패</p>
      )}
    </ChapterPage>
  );
}
