import { getSiteData } from "@/lib/data";

/** 락업 랭킹 한 줄 — IPO 기관 확약 해제일 하나가 한 줄이다.
 *
 *  등락률은 우리가 종가끼리 나누지 않고 배치가 저장해 둔 거래소 등락률(FLUC_RT)을
 *  쓴다. 권리락이 낀 날은 전일 종가가 아니라 기준가 대비로 계산돼야 하는데 그
 *  판단은 거래소 값이 이미 하고 있다.
 *
 *  기관 확약은 15일·1개월·3개월·6개월로 규격이 정해져 있어 종목 간 비교가 된다.
 */
export interface LockupRankingRow {
  code: string;
  name: string;
  market: string;
  period: string;
  releaseDate: string;
  qty: number;
  /** 해제 물량이 상장주식수에서 차지하는 비중 */
  pct: number;
  releaseClose: number;
  /** 해제일 당일 등락률(%) — 거래소 기준 */
  flucRt: number;
  marketCap: number;
}

export const LOCKUP_PERIODS = ["15일", "1개월", "3개월", "6개월"] as const;

export function getLockupRanking(): LockupRankingRow[] {
  const rows: LockupRankingRow[] = [];
  for (const stock of getSiteData().stocks) {
    for (const event of stock.events || []) {
      // 기관 확약만 — 기존주주 보호예수는 기간이 종목마다 제각각이라 비교 대상이 아니다
      if (event.type !== "IPO확약") continue;
      // 해제일 시세를 아직 못 받은 건(캐시 미채움·미래 해제)은 순위에 넣지 않는다
      if (!event.release_close) continue;
      rows.push({
        code: stock.code,
        name: stock.name,
        market: stock.market || "",
        period: event.period,
        releaseDate: event.tradable_date,
        qty: event.qty,
        pct: event.pct,
        releaseClose: event.release_close,
        flucRt: event.release_fluc_rt ?? 0,
        marketCap: stock.market_cap || 0,
      });
    }
  }
  return rows.sort((a, b) => b.flucRt - a.flucRt);
}
