import siteData from "@/data/site_data.json";
import type { SiteData, StockLockup, LockupEvent } from "./types";








export type LockupCategory = "IPO기관" | "기존주주";








export function getSiteData(): SiteData {
  return siteData as SiteData;
}








export function getStockByCode(code: string): StockLockup | undefined {
  return getSiteData().stocks.find((s) => s.code === code);
}








export function getEventCategory(ev: Pick<LockupEvent, "type">): LockupCategory {
  return ev.type === "보호예수" ? "기존주주" : "IPO기관";
}








export interface EventBreakdown {
  category: LockupCategory;
  qty: number;
  pct: number;
  items: LockupEvent[];
}








export interface UpcomingGroup {
  stockCode: string;
  stockName: string;
  market: string;
  listing_date: string;
  shares: number;
  closePrice: number;
  ipoPrice: number;
  tradable_date: string;
  date_display: string;
  periods: string[];
  qty: number;
  pct: number;
  status: string;
  breakdown: EventBreakdown[];
}








// 절대시간(ms)을 한국시간 기준 날짜 번호로 변환 — 서버(UTC)/브라우저 어디서 돌아도 같은 결과
function kstDayNumber(ms: number): number {
  return Math.floor((ms + 9 * 60 * 60 * 1000) / 86400000);
}








export function dDay(dateStr: string, today = new Date()): number {
  const target = kstDayNumber(Date.parse(`${dateStr}T00:00:00+09:00`));
  return target - kstDayNumber(today.getTime());
}








// 사용자에게 보여줄 상태 — 운영용 세부 상태(반환확인_API수정 등) 대신 날짜 기준 두 가지로 단순화
export function displayStatus(tradableDate: string, today = new Date()): "예정" | "해제완료" {
  return dDay(tradableDate, today) >= 0 ? "예정" : "해제완료";
}




const GENERIC_PERIODS = new Set(["", "보호예수", "기존주주", "구주", "구주·보호예수", "기타"]);
const PERIOD_TARGETS = [
  { label: "15일", days: 15, tolerance: 4 },
  { label: "1개월", days: 30, tolerance: 7 },
  { label: "2개월", days: 61, tolerance: 10 },
  { label: "3개월", days: 91, tolerance: 12 },
  { label: "6개월", days: 183, tolerance: 18 },
  { label: "12개월", days: 365, tolerance: 30 },
  { label: "18개월", days: 548, tolerance: 35 },
  { label: "24개월", days: 730, tolerance: 45 },
  { label: "30개월", days: 913, tolerance: 50 },
  { label: "36개월", days: 1095, tolerance: 60 },
];




function inferPeriodFromDates(listingDate: string, releaseDate: string): string {
  const listedAt = Date.parse(`${listingDate}T00:00:00+09:00`);
  const releasedAt = Date.parse(`${releaseDate}T00:00:00+09:00`);
  if (!Number.isFinite(listedAt) || !Number.isFinite(releasedAt)) return "기타";


  const diffDays = Math.max(0, Math.round((releasedAt - listedAt) / 86400000));
  const matched = PERIOD_TARGETS.find((target) => Math.abs(diffDays - target.days) <= target.tolerance);
  return matched?.label || "기타";
}




export function displayPeriod(period: string | null | undefined, listingDate: string, releaseDate: string): string {
  const normalized = (period || "").trim();
  if (normalized && !GENERIC_PERIODS.has(normalized)) return normalized;
  return inferPeriodFromDates(listingDate, releaseDate);
}








function statusOrder(status: string): number {
  if (status === "예정") return 0;
  if (status === "수동확인") return 1;
  if (status === "반환확인") return 2;
  return 3;
}








function groupEventsForStock(stock: StockLockup): UpcomingGroup[] {
  const map = new Map<string, LockupEvent[]>();








  for (const ev of stock.events) {
    const key = ev.tradable_date;
    const current = map.get(key) || [];
    current.push(ev);
    map.set(key, current);
  }








  return [...map.entries()].map(([tradableDate, events]) => {
    const qty = events.reduce((sum, ev) => sum + ev.qty, 0);
    const breakdownMap = new Map<LockupCategory, LockupEvent[]>();








    for (const ev of events) {
      const category = getEventCategory(ev);
      const current = breakdownMap.get(category) || [];
      current.push(ev);
      breakdownMap.set(category, current);
    }








    const breakdown: EventBreakdown[] = (["IPO기관", "기존주주"] as LockupCategory[])
      .map((category) => {
        const items = breakdownMap.get(category) || [];
        const categoryQty = items.reduce((sum, ev) => sum + ev.qty, 0);
        return {
          category,
          items,
          qty: categoryQty,
          pct: stock.shares ? Number(((categoryQty / stock.shares) * 100).toFixed(2)) : 0,
        };
      })
      .filter((b) => b.qty > 0)
      .sort((a, b) => b.qty - a.qty);








    return {
      stockCode: stock.code,
      stockName: stock.name,
      market: stock.market,
      listing_date: stock.listing_date,
      shares: stock.shares,
      closePrice: stock.close_price,
      ipoPrice: stock.ipo_price || 0,
      tradable_date: tradableDate,
      date_display: events[0]?.date_display || tradableDate,
      periods: [...new Set(events.map((ev) => displayPeriod(ev.period, stock.listing_date, ev.tradable_date)))],
      qty,
      pct: stock.shares ? Number(((qty / stock.shares) * 100).toFixed(2)) : 0,
      status: [...events].sort((a, b) => statusOrder(a.status) - statusOrder(b.status))[0]?.status || "예정",
      breakdown,
    };
  });
}








export function getUpcomingEvents(daysAhead = 30, today = new Date()): UpcomingGroup[] {
  const groups: UpcomingGroup[] = [];
  for (const stock of getSiteData().stocks) {
    for (const group of groupEventsForStock(stock)) {
      const d = dDay(group.tradable_date, today);
      if (d >= 0 && d <= daysAhead) groups.push(group);
    }
  }
  return groups.sort((a, b) => dDay(a.tradable_date, today) - dDay(b.tradable_date, today));
}








export function getGroupedEventsByStock(stock: StockLockup, today = new Date()): { upcoming: UpcomingGroup[]; past: UpcomingGroup[] } {
  const groups = groupEventsForStock(stock).sort((a, b) => a.tradable_date.localeCompare(b.tradable_date));
  return {
    upcoming: groups.filter((g) => dDay(g.tradable_date, today) >= 0),
    past: groups.filter((g) => dDay(g.tradable_date, today) < 0),
  };
}








export interface FlatRow {
  code: string;
  name: string;
  market: string;
  shares: number;
  listing_date: string;
  category: LockupCategory;
  period: string;
  date_display: string;
  qty: number;
  pct: number;
  marketCap: number;
  close_price: number;
  status: string;
  tradable_date: string;
  type: string;
  holder_name?: string | null;
  reason?: string | null;
}








export function getFlatRows(): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const stock of getSiteData().stocks) {
    for (const ev of stock.events) {
      rows.push({
        code: stock.code,
        name: stock.name,
        market: stock.market,
        shares: stock.shares,
        listing_date: stock.listing_date,
        category: getEventCategory(ev),
        period: displayPeriod(ev.period, stock.listing_date, ev.tradable_date),
        date_display: ev.date_display,
        qty: ev.qty,
        pct: ev.pct,
        marketCap: stock.shares * stock.close_price,
        close_price: stock.close_price,
        status: ev.status,
        tradable_date: ev.tradable_date,
        type: ev.type,
        holder_name: ev.holder_name,
        reason: ev.reason,
      });
    }
  }
  return rows.sort((a, b) => a.tradable_date.localeCompare(b.tradable_date));
}
