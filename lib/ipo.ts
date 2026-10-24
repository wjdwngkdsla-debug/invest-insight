import ipoData from "@/data/ipo_schedule.json";

// dDay를 자체 정의(lib/data 미의존) — 이 모듈을 클라이언트 컴포넌트에서 import해도
// 무거운 site_data.json이 번들에 딸려오지 않게 한다.
function kstDayNumber(ms: number): number {
  return Math.floor((ms + 9 * 60 * 60 * 1000) / 86400000);
}

export function dDay(dateStr: string, today = new Date()): number {
  const target = kstDayNumber(Date.parse(`${dateStr}T00:00:00+09:00`));
  return target - kstDayNumber(today.getTime());
}

export interface CommitTier {
  period: string;
  qty: number;
  pct: number;
  source?: string;
  visible?: boolean;
}

export interface IpoItem {
  corp_code: string;
  name: string;
  market?: string;
  underwriter?: string;
  band_low?: number;
  band_high?: number;
  final_price?: number;
  offer_shares?: number;
  forecast_start?: string;
  forecast_end?: string;
  sub_start?: string;
  sub_end?: string;
  payment_date?: string;
  listing_date?: string;
  stock_code?: string;
  demand_ratio?: number;
  sub_ratio?: number;
  commit_apply?: CommitTier[];
  commit_alloc?: CommitTier[];
  withdrawn?: boolean;
  content_url?: string; // 시트 IPO일정 탭의 콘텐츠링크 열 (운영자 입력)
  first_filing_date?: string;
  last_rcept_no?: string;
  withdrawn_date?: string;
  offering_attempt?: number; // 과거 철회 후 재공모면 2 이상
  review_pending?: boolean; // IPO 신호 부족 → 검토대기(비공개). 사이트 노출 제외
  manual_entry?: boolean; // 종목관리에서 이름만 먼저 편입한 항목(빈 값은 미정 노출)
  fixed_excluded?: boolean; // 운영자 제외고정. 새 공시가 나와도 자동 부활하지 않음
  management_hidden?: boolean;
  schedule_hidden?: boolean;
  management_status?: string;
}

export interface IpoScheduleData {
  updated: string;
  items: IpoItem[];
  past_items?: IpoItem[];
}

export function getIpoSchedule(): IpoScheduleData {
  return ipoData as IpoScheduleData;
}

export type IpoTone = "active" | "waiting" | "done";
type IpoEventKind = "listing" | "subscription" | "forecast";

interface IpoFocusEvent {
  kind: IpoEventKind;
  day: number;
  active: boolean;
}

const EVENT_PRIORITY: Record<IpoEventKind, number> = {
  listing: 0,
  subscription: 1,
  forecast: 2,
};

// 각 기업에서 지금 진행 중이거나 오늘 이후 가장 가까운 일정 하나를 고른다.
// 같은 날에는 상장 → 청약 → 수요예측 순으로 보여준다.
function ipoFocusEvent(item: IpoItem, today = new Date()): IpoFocusEvent | null {
  const active: IpoFocusEvent[] = [];
  const upcoming: IpoFocusEvent[] = [];
  const addRange = (kind: IpoEventKind, start?: string, end?: string) => {
    if (!start) return;
    const startDay = dDay(start, today);
    const endDay = end ? dDay(end, today) : startDay;
    if (startDay <= 0 && endDay >= 0) {
      active.push({ kind, day: 0, active: true });
    } else if (startDay >= 0) {
      upcoming.push({ kind, day: startDay, active: false });
    }
  };

  if (item.listing_date) {
    const day = dDay(item.listing_date, today);
    if (day === 0) active.push({ kind: "listing", day: 0, active: true });
    else if (day > 0) upcoming.push({ kind: "listing", day, active: false });
  }
  addRange("subscription", item.sub_start, item.sub_end);
  addRange("forecast", item.forecast_start, item.forecast_end);

  const byDateThenType = (a: IpoFocusEvent, b: IpoFocusEvent) =>
    a.day - b.day || EVENT_PRIORITY[a.kind] - EVENT_PRIORITY[b.kind];
  return active.sort(byDateThenType)[0] || upcoming.sort(byDateThenType)[0] || null;
}
// 절대 우선순위: 상장일 확정 종목 → 오늘 진행 중 → 가장 가까운 다음 일정 → 나머지.
// 상장 예정끼리는 상장일이 가까운 순서다.
export function ipoSortKey(item: IpoItem, today = new Date()): [number, number, number, string] {
  if (item.listing_date) {
    const listingDay = dDay(item.listing_date, today);
    if (listingDay >= 0) return [0, listingDay, EVENT_PRIORITY.listing, item.name];
  }
  const event = ipoFocusEvent(item, today);
  if (event) {
    return [event.active ? 1 : 2, event.day, EVENT_PRIORITY[event.kind], item.name];
  }
  return [3, Number.MAX_SAFE_INTEGER, 9, item.name];
}

export function getSortedIpoItems(today = new Date()): IpoItem[] {
  // 검토대기(review_pending) 종목은 사이트 비노출 — 시트에서 승인해야 뜬다
  return [...getIpoSchedule().items]
    .filter((item) => !item.withdrawn && !item.review_pending && !item.fixed_excluded && !item.management_hidden && !item.schedule_hidden)
    .sort((a, b) => {
      const ka = ipoSortKey(a, today);
      const kb = ipoSortKey(b, today);
      return ka[0] - kb[0] || ka[1] - kb[1] || ka[2] - kb[2] || ka[3].localeCompare(kb[3]);
    });
}

export function getPastIpoItems(): IpoItem[] {
  // 다음 배치가 JSON의 철회 종목을 past_items로 옮기기 전이라도 화면에서는 즉시 이력으로 보낸다.
  const schedule = getIpoSchedule();
  const combined = [...(schedule.past_items || []), ...schedule.items.filter((item) => item.withdrawn)];
  const deduped = [...new Map(combined.map((item) => [`${item.corp_code}:${item.last_rcept_no || item.first_filing_date || ""}`, item])).values()];
  return deduped
    .filter((item) => !item.review_pending && !item.fixed_excluded && !item.management_hidden && !item.schedule_hidden)
    .sort(
      (a, b) =>
        (b.withdrawn_date || b.listing_date || b.first_filing_date || "").localeCompare(
          a.withdrawn_date || a.listing_date || a.first_filing_date || ""
        ) ||
        a.name.localeCompare(b.name)
    );
}

// "2026-07-01" → "07.01"
export function mmdd(s?: string): string {
  return s ? s.slice(5).replace("-", ".") : "";
}

export function yymmdd(s?: string): string {
  return s ? s.slice(2).replaceAll("-", ".") : "";
}

export function dateRange(start?: string, end?: string): string {
  if (!start) return "미정";
  if (!end || end === start) return mmdd(start);
  return `${mmdd(start)} ~ ${mmdd(end)}`;
}
// 확정공모가의 밴드 내 위치 표시
export function bandPosition(item: IpoItem): string {
  const { final_price: fp, band_low: lo, band_high: hi } = item;
  if (!fp || !lo || !hi) return "";
  if (fp > hi) return "상단 초과";
  if (fp === hi) return "상단";
  if (fp <= lo) return "하단";
  return "";
}
