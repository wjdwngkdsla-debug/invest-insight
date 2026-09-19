import type { IpoItem } from "./ipo";

export type IpoStage = "upcoming" | "forecast" | "subscription" | "listing" | "listed" | "withdrawn";
export type IpoStageFilter = "all" | "upcoming" | "forecast" | "subscription" | "listing";
export interface IpoStageStatus { stage: IpoStage; label: string }

export function ipoToday(today = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(today);
}

export function ipoStageStatus(item: IpoItem, today: string): IpoStageStatus {
  if (item.withdrawn) return { stage: "withdrawn", label: "공모 철회" };
  if (item.listing_date && item.listing_date < today) return { stage: "listed", label: "상장 완료" };
  if (item.listing_date === today) return { stage: "listing", label: "상장일" };
  const active = (start?: string, end?: string) => Boolean(start && start <= today && (end || start) >= today);
  if (active(item.sub_start, item.sub_end)) return { stage: "subscription", label: "청약" };
  if (active(item.forecast_start, item.forecast_end)) return { stage: "forecast", label: "수요예측" };
  const listing = (): IpoStageStatus => {
    const days = item.listing_date ? Math.round((Date.parse(item.listing_date) - Date.parse(today)) / 86400000) : null;
    return { stage: "listing", label: days === null ? "상장일 미정" : `상장 예정 D-${days}` };
  };
  if (item.sub_end && item.sub_end < today) return listing();
  if (item.forecast_start && item.forecast_start > today) return { stage: "upcoming", label: "공모예정" };
  // The gap after forecasting belongs to subscription, without implying it is open.
  if ((item.forecast_end && item.forecast_end < today) || (item.sub_start && item.sub_start > today)) {
    return { stage: "subscription", label: "청약 예정" };
  }
  if (item.listing_date) return listing();
  return { stage: "upcoming", label: "공모예정" };
}

export function matchesIpoStage(item: IpoItem, query: string, filter: IpoStageFilter, today: string, history: boolean, archived = false): boolean {
  if (item.review_pending || item.fixed_excluded || item.management_hidden || item.schedule_hidden) return false;
  const normalize = (text: string) => text.toLowerCase().replace(/\s+/g, "");
  if (!normalize(`${item.name} ${item.stock_code || ""}`).includes(normalize(query))) return false;
  const { stage } = ipoStageStatus(item, today);
  const past = archived || stage === "listed" || stage === "withdrawn";
  return history ? past : !past && (filter === "all" || stage === filter);
}

const STAGE_ORDER: Record<IpoStage, number> = {
  listing: 0, subscription: 1, forecast: 2, upcoming: 3, listed: 4, withdrawn: 5,
};

export function compareIpoStages(a: IpoItem, b: IpoItem, today: string, history = false): number {
  if (history) {
    const date = (item: IpoItem) => (item.withdrawn_date || item.listing_date || item.first_filing_date || "").replaceAll("-", "");
    return date(b).localeCompare(date(a)) || a.name.localeCompare(b.name, "ko");
  }
  const aStage = ipoStageStatus(a, today).stage;
  const bStage = ipoStageStatus(b, today).stage;
  const group = STAGE_ORDER[aStage] - STAGE_ORDER[bStage];
  if (group) return group;
  const date = (item: IpoItem, stage: IpoStage) => {
    if (stage === "listing") return item.listing_date || "9999-12-31";
    if (stage === "subscription") return item.sub_start || "9999-12-31";
    return item.forecast_start || "9999-12-31";
  };
  return date(a, aStage).localeCompare(date(b, bStage)) || a.name.localeCompare(b.name, "ko");
}

export const IPO_STAGE_STYLE: Record<IpoStage, { color: string }> = {
  upcoming: { color: "bg-blue-50 text-blue-700" },
  forecast: { color: "bg-violet-50 text-violet-500" },
  subscription: { color: "bg-amber-50 text-amber-800" },
  listing: { color: "bg-emerald-50 text-emerald-800" },
  listed: { color: "bg-gray-100 text-gray-500" },
  withdrawn: { color: "bg-gray-100 text-gray-500" },
};
