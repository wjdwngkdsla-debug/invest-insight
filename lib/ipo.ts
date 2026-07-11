import ipoData from "@/data/ipo_schedule.json";
import { dDay } from "./data";

export interface CommitTier {
  period: string;
  qty: number;
  pct: number;
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
}

export interface IpoScheduleData {
  updated: string;
  items: IpoItem[];
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
  return [...getIpoSchedule().items].sort((a, b) => {
    const ka = ipoSortKey(a, today);
    const kb = ipoSortKey(b, today);
    return ka[0] - kb[0] || ka[1].localeCompare(kb[1]) || ka[2].localeCompare(kb[2]);
  });
}

// "2026-07-01" → "07.01"
export function mmdd(s?: string): string {
  return s ? s.slice(5).replace("-", ".") : "";
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
