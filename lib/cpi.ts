import { fetchFredSeries } from "./fred";
import { fetchEcosStat } from "./ecos";
import { alignToCommonQuarters, appendNaiveEstimate, monthToQuarter, toQuarterlySeries } from "./quarterly";
import type { CountrySeries } from "./types";

const QUARTER_COUNT = 12; // 최근 3개년(분기별)

// CPI 지수(레벨) 시리즈 — 전년동월비(YoY)는 아래에서 직접 계산
// 주의: 일본(JPNCPIALLMINMEI)은 FRED 공급이 2021-06 이후 값이 전부 "."(결측)이고,
// 중국(CHNCPIALLMINMEI)은 2025-04 이후 갱신이 끊겨 있다. 공통 3개년 축에 넣으면
// 최신 데이터가 있는 한국/미국/유럽까지 옛날 시점으로 잘려버리므로,
// 두 나라는 공통 축에서 빼고 자체 최신 12분기(=각자의 마지막 실측 시점 기준)를 따로 표시한다.
const FRED_CPI_INDEX_SERIES: Record<string, string> = {
  US: "CPIAUCSL",
  EU: "CP0000EZ19M086NEST",
};
const STALE_FRED_CPI_SERIES: Record<string, string> = {
  JP: "JPNCPIALLMINMEI",
  CN: "CHNCPIALLMINMEI",
};

const LABELS: Record<string, { label: string; flag: string }> = {
  US: { label: "미국", flag: "🇺🇸" },
  KR: { label: "한국", flag: "🇰🇷" },
  JP: { label: "일본", flag: "🇯🇵" },
  EU: { label: "유럽", flag: "🇪🇺" },
  CN: { label: "중국", flag: "🇨🇳" },
};

// 지수 레벨 배열(오래된 순)에서 YoY(%)를 계산 (월별 기준, 12개월 전 대비)
function toYoy(dates: string[], values: number[]): { period: string; value: number; refMonth: string }[] {
  const out: { period: string; value: number; refMonth: string }[] = [];
  for (let i = 12; i < values.length; i++) {
    if (values[i] == null || values[i - 12] == null) continue;
    const yoy = ((values[i] - values[i - 12]) / values[i - 12]) * 100;
    out.push({
      period: monthToQuarter(dates[i].replace(/-/g, "").slice(0, 6)),
      value: Math.round(yoy * 100) / 100,
      refMonth: dates[i].slice(0, 7),
    });
  }
  return out;
}

async function fetchFredCpiYoyPoints(seriesId: string) {
  const obs = await fetchFredSeries(seriesId, { limit: 80 });
  const dates = obs.map((o) => o.date);
  const values = obs.map((o) => (o.value === "." ? null : Number(o.value))) as number[];
  return toYoy(dates, values);
}

async function fetchKoreaCpiYoyPoints() {
  const now = new Date();
  const endPeriod = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;
  const rows = await fetchEcosStat({
    statCode: "901Y009",
    itemCode1: "0",
    cycle: "M",
    startPeriod: "202001",
    endPeriod,
    count: 100,
  });

  const dates = rows.map((r) => `${r.TIME.slice(0, 4)}-${r.TIME.slice(4, 6)}-01`);
  const values = rows.map((r) => Number(r.DATA_VALUE));
  return toYoy(dates, values);
}

function latestOf<T extends { period: string }>(points: T[]): T | undefined {
  return [...points].sort((a, b) => a.period.localeCompare(b.period)).at(-1);
}

export async function fetchAllCpi(): Promise<CountrySeries[]> {
  const [krPoints, ...fredEntries] = await Promise.all([
    fetchKoreaCpiYoyPoints(),
    ...Object.entries(FRED_CPI_INDEX_SERIES).map(async ([country, seriesId]) => ({
      country,
      points: await fetchFredCpiYoyPoints(seriesId),
    })),
  ]);

  const commonRaw = [{ country: "KR", points: krPoints }, ...fredEntries];

  const aligned = alignToCommonQuarters(
    commonRaw.map((c) => ({ key: c.country, points: c.points })),
    QUARTER_COUNT
  );

  const commonResults: CountrySeries[] = commonRaw.map((c) => {
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

  // 데이터 공급이 끊긴 국가(일본/중국)는 공통 축에서 빼고 자체 최신 시점으로 별도 표시
  const staleResults = await Promise.all(
    Object.entries(STALE_FRED_CPI_SERIES).map(async ([country, seriesId]) => {
      try {
        const points = await fetchFredCpiYoyPoints(seriesId);
        let series = toQuarterlySeries(points, QUARTER_COUNT);
        series = appendNaiveEstimate(series);
        const lastActual = latestOf(points);
        const result: CountrySeries = {
          country: country as CountrySeries["country"],
          label: LABELS[country].label,
          flag: LABELS[country].flag,
          charted: true,
          series,
          current: lastActual?.value ?? null,
          currentPeriod: lastActual?.refMonth,
        };
        return result;
      } catch {
        return null;
      }
    })
  );

  return [...commonResults, ...staleResults.filter((r): r is CountrySeries => r !== null)];
}
