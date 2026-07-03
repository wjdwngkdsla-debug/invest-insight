import type { TimeSeriesPoint } from "./types";

// YYYYMM -> YYYYQn
export function monthToQuarter(yyyymm: string): string {
  const year = yyyymm.slice(0, 4);
  const month = Number(yyyymm.slice(4, 6));
  const q = Math.ceil(month / 3);
  return `${year}Q${q}`;
}

// YYYY-MM-DD -> YYYYQn
export function dateToQuarter(dateStr: string): string {
  const year = dateStr.slice(0, 4);
  const month = Number(dateStr.slice(5, 7));
  const q = Math.ceil(month / 3);
  return `${year}Q${q}`;
}

/**
 * (기간, 값) 목록을 분기별 마지막 값 기준으로 묶고, 최근 N개 분기만 남긴다.
 */
export function toQuarterlySeries(
  points: { period: string; value: number }[],
  quarterCount = 10
): TimeSeriesPoint[] {
  const byQuarter = new Map<string, number>();
  for (const p of points) {
    byQuarter.set(p.period, p.value); // 뒤에 오는 값(=분기 내 최신값)으로 덮어씀
  }

  const sortedQuarters = Array.from(byQuarter.keys()).sort();
  const lastN = sortedQuarters.slice(-quarterCount);

  return lastN.map((period) => ({ period, value: byQuarter.get(period) ?? null }));
}

/**
 * 마지막 두 분기의 변화량을 이용해 다음 분기 추정치를 단순 선형 연장한다.
 * (공공/무료 API로는 시장 컨센서스를 구하기 어려워 임시로 쓰는 방식)
 */
export function appendNaiveEstimate(series: TimeSeriesPoint[]): TimeSeriesPoint[] {
  if (series.length < 2) return series;

  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (last.value == null || prev.value == null) return series;

  const nextPeriod = nextQuarter(last.period);
  const delta = last.value - prev.value;
  const estimate = Math.round((last.value + delta) * 100) / 100;

  return [...series, { period: nextPeriod, value: estimate, isEstimate: true }];
}

export function nextQuarter(period: string): string {
  const [year, q] = period.split("Q").map(Number);
  const nextQ = q === 4 ? 1 : q + 1;
  const nextYear = q === 4 ? year + 1 : year;
  return `${nextYear}Q${nextQ}`;
}

function prevQuarter(period: string): string {
  const [year, q] = period.split("Q").map(Number);
  const prevQ = q === 1 ? 4 : q - 1;
  const prevYear = q === 1 ? year - 1 : year;
  return `${prevYear}Q${prevQ}`;
}

export interface RawCountrySeries {
  key: string;
  points: { period: string; value: number }[]; // 오래된 순
}

/**
 * 여러 국가의 원본 분기 시계열을 받아, "모든 국가가 실측치를 가진 마지막 분기"를
 * 공통 종료 시점으로 잡고 동일한 길이의 분기 축으로 정렬한다.
 * 그 다음 분기(아직 발표 전)는 각국 자체 추세로 추정해 하나씩 덧붙인다.
 */
export function alignToCommonQuarters(
  countries: RawCountrySeries[],
  quarterCount: number
): Map<string, TimeSeriesPoint[]> {
  const maps = countries.map((c) => new Map(c.points.map((p) => [p.period, p.value])));

  const latestPerCountry = maps
    .map((m) => Array.from(m.keys()).sort().pop())
    .filter((v): v is string => !!v);
  if (latestPerCountry.length === 0) return new Map();

  const commonEnd = latestPerCountry.sort()[0]; // 가장 늦게 갱신되는 국가 기준(보수적)

  const axis: string[] = [commonEnd];
  for (let i = 1; i < quarterCount; i++) {
    axis.unshift(prevQuarter(axis[0]));
  }

  const estimatePeriod = nextQuarter(commonEnd);

  const result = new Map<string, TimeSeriesPoint[]>();
  countries.forEach((c, i) => {
    const map = maps[i];
    const series: TimeSeriesPoint[] = axis.map((period) => ({
      period,
      value: map.get(period) ?? null,
    }));

    const withEstimate = appendNaiveEstimate(series);
    // appendNaiveEstimate가 만든 추정치 기간을 공통 추정치 기간으로 맞춘다
    if (withEstimate.length > series.length) {
      withEstimate[withEstimate.length - 1].period = estimatePeriod;
    }

    result.set(c.key, withEstimate);
  });

  return result;
}
