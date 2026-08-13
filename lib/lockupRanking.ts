import { getSiteData } from "@/lib/data";

export const LOCKUP_PERIODS = ["15일", "1개월", "3개월", "6개월"] as const;
export type LockupPeriod = (typeof LOCKUP_PERIODS)[number];

/** 기관 확약 해제일 수익률을 종목당 한 행으로 모은 비교표. */
export interface LockupRankingRow {
  code: string;
  name: string;
  market: string;
  marketCap: number;
  returns: Record<LockupPeriod, number | null>;
}

export function getLockupRanking(): LockupRankingRow[] {
  const rows: LockupRankingRow[] = [];
  for (const stock of getSiteData().stocks) {
    const returns = Object.fromEntries(LOCKUP_PERIODS.map((period) => [period, null])) as Record<
      LockupPeriod,
      number | null
    >;
    let hasReleasePrice = false;

    for (const event of stock.events || []) {
      if (event.type !== "IPO확약" || !LOCKUP_PERIODS.includes(event.period as LockupPeriod)) continue;
      if (!event.release_close || event.release_fluc_rt === undefined || event.release_fluc_rt === null) continue;
      returns[event.period as LockupPeriod] = event.release_fluc_rt;
      hasReleasePrice = true;
    }
    if (!hasReleasePrice) continue;
    rows.push({
      code: stock.code,
      name: stock.name,
      market: stock.market || "",
      marketCap: stock.market_cap || 0,
      returns,
    });
  }
  return rows;
}
