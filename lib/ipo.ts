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

export interface IpoStatus {
  label: string;
  tone: IpoTone;
}

// 오늘 뭔가 진행 중 = 빨강(active), 대기 = 파랑(waiting), 끝난 상태 = 회색(done)
export function ipoStatus(item: IpoItem, today = new Date()): IpoStatus {
  if (item.withdrawn) return { label: "공모 철회", tone: "done" };
  const d = (s?: string) => (s ? dDay(s, today) : null);

  const listing = d(item.listing_date);
  if (listing !== null && listing < 0) return { label: "상장 완료", tone: "done" };
  if (listing !== null) return { label: listing === 0 ? "오늘 상장" : `상장 D-${listing}`, tone: "waiting" };

  const subStart = d(item.sub_start);
  const subEnd = d(item.sub_end);
  if (subStart !== null && subStart <= 0 && subEnd !== null && subEnd >= 0) return { label: "청약 중", tone: "active" };
  // 확정공모가 없이 청약일만 지난 경우 = 공모가 확정 없이 청약이 진행될 수 없으므로 일정 연기로 본다
  if (subEnd !== null && subEnd < 0 && !item.final_price) return { label: "일정 미정", tone: "waiting" };
  if (subEnd !== null && subEnd < 0) return { label: "청약 완료", tone: "done" };

  const fcStart = d(item.forecast_start);
  const fcEnd = d(item.forecast_end);
  if (fcStart !== null && fcStart <= 0 && fcEnd !== null && fcEnd >= 0) return { label: "수요예측 중", tone: "active" };
  if (fcEnd !== null && fcEnd < 0) return { label: "청약 예정", tone: "waiting" };
  if (fcStart !== null) return { label: "수요예측 예정", tone: "waiting" };
  return { label: "공모 준비", tone: "waiting" };
}

// 노출 우선순위: 임박한 상장일 → 임박한 청약일 → 임박한 수요예측일 → 나머지 → 철회
export function ipoSortKey(item: IpoItem, today = new Date()): [number, string, string] {
  if (item.withdrawn) return [4, "", item.name];
  if (item.listing_date && dDay(item.listing_date, today) >= 0) return [0, item.listing_date, item.name];
  if (item.sub_start && dDay(item.sub_start, today) >= 0) return [1, item.sub_start, item.name];
  if (item.forecast_start && dDay(item.forecast_start, today) >= 0) return [2, item.forecast_start, item.name];
  return [3, item.first_filing_date || "", item.name];
}

export function getSortedIpoItems(today = new Date()): IpoItem[] {
  // 검토대기(review_pending) 종목은 사이트 비노출 — 시트에서 승인해야 뜬다
  return [...getIpoSchedule().items]
    .filter((item) => !item.review_pending && !item.fixed_excluded && !item.management_hidden && !item.schedule_hidden)
    .sort((a, b) => {
      const ka = ipoSortKey(a, today);
      const kb = ipoSortKey(b, today);
      return ka[0] - kb[0] || ka[1].localeCompare(kb[1]) || ka[2].localeCompare(kb[2]);
    });
}

export function getPastIpoItems(): IpoItem[] {
  return [...(getIpoSchedule().past_items || [])]
    .filter((item) => !item.review_pending && !item.fixed_excluded && !item.management_hidden && !item.schedule_hidden)
    .sort(
      (a, b) =>
        (b.listing_date || "").localeCompare(a.listing_date || "") ||
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

export function dateRangeWithYear(start?: string, end?: string): string {
  if (!start) return "미정";
  if (!end || end === start) return yymmdd(start);
  return `${yymmdd(start)} ~ ${yymmdd(end)}`;
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
