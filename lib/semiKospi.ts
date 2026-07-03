import { fetchSemiconductorExports } from "./itemtrade";
import { fetchKospiHistory } from "./kospi";
import { correlation } from "./stats";
import { toEok } from "./format";
import { lastCompletedYymm, yymmMonthsAgo } from "./dateUtils";
import type { DualAxisSeries } from "./types";

export async function fetchSemiconductorVsKospi(): Promise<DualAxisSeries> {
  const endYymm = lastCompletedYymm(); // 이번 달은 수출 집계가 미완결이라 제외
  const startYymm = yymmMonthsAgo(23, endYymm);

  const [semiExports, kospiDaily] = await Promise.all([
    fetchSemiconductorExports({ startYymm, endYymm }),
    fetchKospiHistory("2y"),
  ]);

  // KOSPI 월말 종가로 축약
  const kospiByMonth = new Map<string, number>();
  for (const p of kospiDaily) {
    const ym = p.date.slice(0, 7);
    kospiByMonth.set(ym, p.close); // 뒤에 오는 값(월 내 최신)으로 덮어씀
  }

  const data = [];
  const leftVals: number[] = [];
  const rightVals: number[] = [];

  for (const { period, exportAmount } of semiExports) {
    const kospi = kospiByMonth.get(period);
    if (kospi == null) continue;
    const exportEok = toEok(exportAmount);
    data.push({ period, left: exportEok, right: Math.round(kospi * 100) / 100 });
    leftVals.push(exportEok);
    rightVals.push(kospi);
  }

  return {
    title: "반도체 수출액 ↔ KOSPI",
    leftLabel: "반도체 수출액(억 달러, 주요국 합산)",
    rightLabel: "KOSPI",
    data,
    correlation: correlation(leftVals, rightVals),
    rightColor: "#dc2626",
  };
}
