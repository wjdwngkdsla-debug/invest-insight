import { getSiteData } from "@/lib/data";

export const LOCKUP_PERIODS = ["15일", "1개월", "3개월", "6개월"] as const;
export type LockupPeriod = (typeof LOCKUP_PERIODS)[number];

/** 기관 확약 해제일 수익률을 종목당 한 행으로 모은 비교표. */
export interface LockupRankingRow {
  code: string;
  name: string;
  market: string;
  listingDate: string;
  marketCap: number;
  returns: Record<LockupPeriod, number | null>;
  /** 확약 자체가 없던 구간. 값이 없는 이유가 "미수집"이 아니라 "해당 없음"이다. */
  absent: Record<LockupPeriod, boolean>;
}

export function getLockupRanking(): LockupRankingRow[] {
  const rows: LockupRankingRow[] = [];
  for (const stock of getSiteData().stocks) {
    const returns = Object.fromEntries(LOCKUP_PERIODS.map((period) => [period, null])) as Record<
      LockupPeriod,
      number | null
    >;
    // 확약이 있었던 구간만 표시 후보다. 모든 종목이 네 구간을 다 쓰는 게 아니라
    // 수요예측에서 그 구간 확약이 0이면 이벤트 자체가 없다(전체 564칸 중 105칸).
    const absent = Object.fromEntries(LOCKUP_PERIODS.map((period) => [period, true])) as Record<
      LockupPeriod,
      boolean
    >;
    let hasReleasePrice = false;

    for (const event of stock.events || []) {
      if (event.type !== "IPO확약" || !LOCKUP_PERIODS.includes(event.period as LockupPeriod)) continue;
      absent[event.period as LockupPeriod] = false;
      if (!event.release_close || event.release_fluc_rt === undefined || event.release_fluc_rt === null) continue;
      returns[event.period as LockupPeriod] = event.release_fluc_rt;
      hasReleasePrice = true;
    }
    if (!hasReleasePrice) continue;
    rows.push({
      code: stock.code,
      name: stock.name,
      market: stock.market || "",
      listingDate: stock.listing_date || "",
      marketCap: stock.market_cap || 0,
      returns,
      absent,
    });
  }
  return rows;
}
