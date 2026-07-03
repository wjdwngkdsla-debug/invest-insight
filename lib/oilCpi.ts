import { fetchFredSeries } from "./fred";
import { fetchEcosStat } from "./ecos";
import { correlation } from "./stats";
import type { DualAxisSeries } from "./types";

// CPI 지수(레벨) -> YoY(%) 계산 공용 함수
function toYoyMap(dates: string[], values: (number | null)[]): Map<string, number> {
  const map = new Map<string, number>();
  for (let i = 12; i < values.length; i++) {
    if (values[i] == null || values[i - 12] == null) continue;
    const yoy = ((values[i]! - values[i - 12]!) / values[i - 12]!) * 100;
    map.set(dates[i].slice(0, 7), Math.round(yoy * 100) / 100);
  }
  return map;
}

export async function fetchOilVsCpi(): Promise<DualAxisSeries> {
  const oilObs = await fetchFredSeries("DCOILWTICO", { limit: 900 }); // 일별 -> 월평균으로 축약(실제 관측치)
  const now = new Date();
  const endPeriod = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;

  const [krCpiRows, usCpiObs] = await Promise.all([
    fetchEcosStat({
      statCode: "901Y009",
      itemCode1: "0",
      cycle: "M",
      startPeriod: "202101",
      endPeriod,
      count: 100,
    }),
    fetchFredSeries("CPIAUCSL", { limit: 100 }), // 미국 CPI 지수
  ]);

  // 유가 월평균 집계 (YYYY-MM -> avg), 실제 관측치 그대로 사용
  const oilByMonth = new Map<string, number>();
  const monthBuckets = new Map<string, number[]>();
  for (const o of oilObs) {
    if (o.value === ".") continue;
    const ym = o.date.slice(0, 7);
    const arr = monthBuckets.get(ym) ?? [];
    arr.push(Number(o.value));
    monthBuckets.set(ym, arr);
  }
  for (const [ym, vals] of monthBuckets) {
    oilByMonth.set(ym, Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100);
  }

  // 한국 CPI YoY(%)
  const krDates = krCpiRows.map((r) => `${r.TIME.slice(0, 4)}-${r.TIME.slice(4, 6)}-01`);
  const krValues = krCpiRows.map((r) => Number(r.DATA_VALUE));
  const krCpiYoy = toYoyMap(krDates, krValues);

  // 미국 CPI YoY(%)
  const usDates = usCpiObs.map((o) => o.date);
  const usValues = usCpiObs.map((o) => (o.value === "." ? null : Number(o.value)));
  const usCpiYoy = toYoyMap(usDates, usValues);

  // 유가·한국CPI·미국CPI를 같은 달(실제 관측월) 기준으로 그대로 정렬 — 인위적 시차 이동 없음
  const data = [];
  const leftVals: number[] = [];
  const rightVals: number[] = [];

  for (const [ym, oilAvg] of Array.from(oilByMonth.entries()).sort(([a], [b]) => a.localeCompare(b))) {
    const krCpi = krCpiYoy.get(ym);
    if (krCpi === undefined) continue;
    const usCpi = usCpiYoy.get(ym) ?? null;
    data.push({ period: ym, left: oilAvg, right: krCpi, right2: usCpi });
    leftVals.push(oilAvg);
    rightVals.push(krCpi);
  }

  return {
    title: "유가(WTI, 실제 월평균) ↔ 한국·미국 CPI YoY",
    leftLabel: "WTI 유가($/배럴)",
    rightLabel: "한국 CPI YoY(%)",
    right2Label: "미국 CPI YoY(%)",
    right2Color: "#dc2626",
    data: data.slice(-36),
    correlation: correlation(leftVals, rightVals),
  };
}
