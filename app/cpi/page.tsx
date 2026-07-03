import { ChapterPage } from "@/components/ChapterPage";
import { CountryIndicatorCard } from "@/components/CountryIndicatorCard";
import { fetchAllCpi } from "@/lib/cpi";

export const revalidate = 86400;

export default async function CpiPage() {
  const cpi = await fetchAllCpi().catch(() => null);

  return (
    <ChapterPage
      eyebrow="INFLATION"
      title="소비자물가지수 CPI (국가별, YoY)"
      description="최근 3개년 분기별 CPI 전년동월비를 국가별로 비교합니다. 일본은 FRED 데이터 공급이 2022년 이후 끊겨 있어 최신 시점까지 표시되지 않습니다."
    >
      {cpi ? (
        <CountryIndicatorCard unit="%" countries={cpi} />
      ) : (
        <p className="text-ink-muted-48">데이터 로딩 실패</p>
      )}
    </ChapterPage>
  );
}
