import { getSiteData } from "@/lib/data";
import { getIpoSchedule } from "@/lib/ipo";
import { currentIpoReturnPct, listingFloatPct, priceReturnPct } from "@/lib/returns";

/** IPO 랭킹 한 줄 — 공모가 대비 수익률을 중심으로 공모 지표를 함께 본다.
 *
 *  가격(공모가·종가·시가총액)은 site_data(KRX 스냅샷), 경쟁률은 ipo_schedule(DART)에
 *  있으므로 종목코드로 이어 붙인다. 순위는 화면에서 기간·시장 필터를 적용한 뒤
 *  매기므로 여기서는 부여하지 않는다.
 */
export interface IpoRankingRow {
  code: string;
  name: string;
  market: string;
  listingDate: string;
  ipoPrice: number;
  closePrice: number;
  returnPct: number | null;
  /** 공모가 대비 상장일 종가 수익률. 상장일 시세를 못 받은 종목은 null */
  listingReturnPct: number | null;
  /** 상장 당일 매도 제한이 없던 물량 비중. 락업 데이터가 없으면 null */
  listingFloatPct: number | null;
  demandRatio: number;
  subRatio: number;
  marketCap: number;
  suspended: boolean;
}

export function getIpoRanking(): IpoRankingRow[] {
  const stocks = new Map(getSiteData().stocks.map((stock) => [stock.code, stock]));
  const schedule = getIpoSchedule();
  const items = [...(schedule.items || []), ...(schedule.past_items || [])];

  const rows: IpoRankingRow[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const code = (item.stock_code || "").trim();
    if (!code || seen.has(code)) continue;
    const stock = stocks.get(code);
    if (!stock) continue; // 락업 데이터가 없는 종목 = 아직 상장 전
    // 공모가는 배치가 확정한 값(site_data) 우선, 없으면 IPO일정의 확정공모가로 보완
    const ipoPrice = stock.ipo_price || item.final_price || 0;
    const closePrice = stock.close_price || 0;
    const listingDate = stock.listing_date || item.listing_date || "";
    if (!ipoPrice || !closePrice || !listingDate) continue;
    if (item.withdrawn) continue;

    seen.add(code);
    rows.push({
      code,
      name: item.name || stock.name,
      market: stock.market || item.market || "",
      listingDate,
      ipoPrice,
      closePrice,
      returnPct: currentIpoReturnPct({
        ipo_price: ipoPrice,
        adjusted_ipo_price: stock.adjusted_ipo_price,
        close_price: closePrice,
        trading_suspended: stock.trading_suspended,
      }),
      listingReturnPct: priceReturnPct(ipoPrice, stock.listing_close || 0),
      listingFloatPct: listingFloatPct(stock),
      demandRatio: item.demand_ratio || 0,
      subRatio: item.sub_ratio || 0,
      marketCap: stock.market_cap || stock.shares * closePrice,
      suspended: Boolean(stock.trading_suspended),
    });
  }
  return rows.sort((a, b) => (b.returnPct ?? -Infinity) - (a.returnPct ?? -Infinity));
}
