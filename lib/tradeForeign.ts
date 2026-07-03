import { fetchCustomsTradeTotal } from "./customs";
import { fetchForeignNetBuyHistory } from "./naver";
import { correlation } from "./stats";
import { toEok } from "./format";
import { lastCompletedYymm, yymmMonthsAgo } from "./dateUtils";
import type { DualAxisSeries } from "./types";

const MONTHS_BACK = 14;

export async function fetchTradeBalanceVsForeign(): Promise<DualAxisSeries> {
  const endYymm = lastCompletedYymm(); // 이번 달은 무역수지가 미완결이라 제외
  const startYymm = yymmMonthsAgo(MONTHS_BACK - 1, endYymm);

  const [trade, foreignDaily] = await Promise.all([
    fetchCustomsTradeTotal({ startYymm, endYymm }),
    fetchForeignNetBuyHistory(MONTHS_BACK),
  ]);

  // 네이버 일별 데이터를 월별로 합산
  const foreignByMonth = new Map<string, number>();
  for (const row of foreignDaily) {
    // date: "26.06.30" -> "2026-06"
    const [yy, mm] = row.date.split(".");
    const ym = `20${yy}-${mm}`;
    foreignByMonth.set(ym, (foreignByMonth.get(ym) ?? 0) + row.foreignNetBuy);
  }

  const tradeByMonth = new Map(trade.map((t) => [t.period, t.tradeBalance]));

  const data = [];
  const leftVals: number[] = [];
  const rightVals: number[] = [];

  for (const [ym, foreignSum] of Array.from(foreignByMonth.entries()).sort()) {
    const balance = tradeByMonth.get(ym);
    if (balance == null) continue;
    const balanceEok = toEok(balance); // 무역수지: 달러 -> 억 달러
    data.push({
      period: ym,
      left: balanceEok,
      right: foreignSum, // 네이버 원본 데이터가 이미 억원 단위
    });
    leftVals.push(balanceEok);
    rightVals.push(foreignSum);
  }

  return {
    title: "무역수지 ↔ 외국인 순매수",
    leftLabel: "무역수지(억 달러)",
    rightLabel: "외국인 순매수(억원)",
    data,
    correlation: correlation(leftVals, rightVals),
  };
}
