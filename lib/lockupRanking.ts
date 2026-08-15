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
  /** 구간별 빈칸의 이유 — 표시 문구가 달라진다. */
  state: Record<LockupPeriod, "none" | "upcoming" | "missing" | "ok">;
}

export function getLockupRanking(): LockupRankingRow[] {
  const rows: LockupRankingRow[] = [];
  // 정적 생성 시점 기준. 하루 단위 구분이라 빌드 후 하루 지나도 표시가 크게 틀어지지 않는다.
  const today = new Date().toISOString().slice(0, 10);
  for (const stock of getSiteData().stocks) {
    const returns = Object.fromEntries(LOCKUP_PERIODS.map((period) => [period, null])) as Record<
      LockupPeriod,
      number | null
    >;
    // 빈칸이 세 가지 뜻으로 섞이면 읽는 사람이 알 수 없다.
    //   none     그 구간 확약이 아예 없었다 (모든 종목이 네 구간을 다 쓰지 않는다)
    //   upcoming 해제일이 아직 안 왔다
    //   missing  해제일은 지났는데 그날 시세를 못 받았다
    const state = Object.fromEntries(LOCKUP_PERIODS.map((period) => [period, "none"])) as Record<
      LockupPeriod,
      "none" | "upcoming" | "missing" | "ok"
    >;
    let hasReleasePrice = false;

    for (const event of stock.events || []) {
      if (event.type !== "IPO확약" || !LOCKUP_PERIODS.includes(event.period as LockupPeriod)) continue;
      const period = event.period as LockupPeriod;
      if (event.release_close && event.release_fluc_rt !== undefined && event.release_fluc_rt !== null) {
        returns[period] = event.release_fluc_rt;
        state[period] = "ok";
        hasReleasePrice = true;
      } else {
        state[period] = event.tradable_date > today ? "upcoming" : "missing";
      }
    }
    if (!hasReleasePrice) continue;
    rows.push({
      code: stock.code,
      name: stock.name,
      market: stock.market || "",
      listingDate: stock.listing_date || "",
      marketCap: stock.market_cap || 0,
      returns,
      state,
    });
  }
  return rows;
}
