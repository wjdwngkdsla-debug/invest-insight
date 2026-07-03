import { fetchFredSeries } from "./fred";
import { fetchEcosStat } from "./ecos";
import { alignToCommonQuarters, monthToQuarter } from "./quarterly";
import type { CountrySeries } from "./types";

const QUARTER_COUNT = 10;

// 차트에 표시할 5개국의 FRED 시리즈 ID (한국 제외, 한국은 ECOS)
const FRED_RATE_SERIES: Record<string, { seriesId: string; limit: number }> = {
  US: { seriesId: "FEDFUNDS", limit: 60 }, // 미국 연방기금금리(실효, 월별)
  JP: { seriesId: "IRSTCI01JPM156N", limit: 60 }, // 일본 콜금리(월별)
  EU: { seriesId: "ECBDFR", limit: 1500 }, // ECB 예금금리(일별) — 분기 환산을 위해 넉넉히 조회
  CN: { seriesId: "IR3TIB01CNM156N", limit: 60 }, // 중국 3개월 은행간금리(월별, 정책금리 대용. 갱신이 더 빠름)
};

// 표에만 노출할 추가국 (FRED 단기금리 계열, 국가별로 갱신주기가 다를 수 있음)
const FRED_TABLE_ONLY_SERIES: Record<string, { seriesId: string; limit: number }> = {
  GB: { seriesId: "IUDSOIA", limit: 60 }, // 영국 SONIA
  IN: { seriesId: "INTDSRINM193N", limit: 60 }, // 인도 재할인율 계열
  BR: { seriesId: "IR3TIB01BRM156N", limit: 60 }, // 브라질 3개월 은행간금리
};

const LABELS: Record<string, { label: string; flag: string }> = {
  US: { label: "미국", flag: "🇺🇸" },
  KR: { label: "한국", flag: "🇰🇷" },
  JP: { label: "일본", flag: "🇯🇵" },
  EU: { label: "유럽", flag: "🇪🇺" },
  CN: { label: "중국", flag: "🇨🇳" },
  GB: { label: "영국", flag: "🇬🇧" },
  IN: { label: "인도", flag: "🇮🇳" },
  BR: { label: "브라질", flag: "🇧🇷" },
};

interface RawPoint {
  period: string;
  value: number;
  refMonth: string;
}

async function fetchFredQuarterlyPoints(seriesId: string, limit: number): Promise<RawPoint[]> {
  const obs = await fetchFredSeries(seriesId, { limit });
  return obs
    .filter((o) => o.value !== ".")
    .map((o) => ({
      period: monthToQuarter(o.date.replace(/-/g, "").slice(0, 6)),
      value: Number(o.value),
      refMonth: o.date.slice(0, 7),
    }));
}

async function fetchKoreaQuarterlyPoints(): Promise<RawPoint[]> {
  const now = new Date();
  const endPeriod = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;

  const rows = await fetchEcosStat({
    statCode: "722Y001",
    itemCode1: "0101000",
    cycle: "M",
    startPeriod: "202101",
    endPeriod,
    count: 100,
  });

  return rows.map((r) => ({
    period: monthToQuarter(r.TIME),
    value: Number(r.DATA_VALUE),
    refMonth: `${r.TIME.slice(0, 4)}-${r.TIME.slice(4, 6)}`,
  }));
}

function latestOf(points: RawPoint[]): RawPoint | undefined {
  return [...points].sort((a, b) => a.period.localeCompare(b.period)).at(-1);
}

export async function fetchAllBaseRates(): Promise<CountrySeries[]> {
  const [krPoints, ...fredEntries] = await Promise.all([
    fetchKoreaQuarterlyPoints(),
    ...Object.entries(FRED_RATE_SERIES).map(async ([country, { seriesId, limit }]) => ({
      country,
      points: await fetchFredQuarterlyPoints(seriesId, limit),
    })),
  ]);

  const chartedRaw = [{ country: "KR", points: krPoints }, ...fredEntries];

  const aligned = alignToCommonQuarters(
    chartedRaw.map((c) => ({ key: c.country, points: c.points })),
    QUARTER_COUNT
  );

  const chartedResults: CountrySeries[] = chartedRaw.map((c) => {
    const lastActual = latestOf(c.points);
    return {
      country: c.country as CountrySeries["country"],
      label: LABELS[c.country].label,
      flag: LABELS[c.country].flag,
      charted: true,
      series: aligned.get(c.country) ?? [],
      current: lastActual?.value ?? null,
      currentPeriod: lastActual?.refMonth,
    };
  });

  const tableOnlyResults = await Promise.all(
    Object.entries(FRED_TABLE_ONLY_SERIES).map(async ([country, { seriesId, limit }]) => {
      try {
        const points = await fetchFredQuarterlyPoints(seriesId, limit);
        const lastActual = latestOf(points);
        const result: CountrySeries = {
          country: country as CountrySeries["country"],
          label: LABELS[country].label,
          flag: LABELS[country].flag,
          charted: false,
          series: [],
          current: lastActual?.value ?? null,
          currentPeriod: lastActual?.refMonth,
        };
        return result;
      } catch {
        return null;
      }
    })
  );

  return [...chartedResults, ...tableOnlyResults.filter((r): r is CountrySeries => r !== null)];
}
