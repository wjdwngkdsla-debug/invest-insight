import type { IpoItem } from "./ipo";

export type IpoPhase = "upcoming" | "subscription" | "forecast" | "waiting" | "listed" | "withdrawn" | "unscheduled";
export type IpoFilter = "active" | "all" | IpoPhase;
export function ipoPhase(item: IpoItem, today: string): IpoPhase {
  if (item.withdrawn) return "withdrawn";
  if (item.listing_date && item.listing_date <= today) return "listed";
  if (item.sub_start && item.sub_start <= today && (item.sub_end || item.sub_start) >= today) return "subscription";
  if (item.forecast_start && item.forecast_start <= today && (item.forecast_end || item.forecast_start) >= today) return "forecast";
  if (item.sub_start && item.sub_start > today) return "upcoming";
  if (item.listing_date || (item.sub_end && item.sub_end < today && item.final_price)) return "waiting";
  if (item.forecast_start && item.forecast_start > today) return "upcoming";
  return "unscheduled";
}

export function matchesIpo(item: IpoItem, query: string, filter: IpoFilter, today: string) {
  if (item.review_pending || item.fixed_excluded || item.management_hidden || item.schedule_hidden) return false;
  const normalize = (value: string) => value.toLocaleLowerCase().replace(/\s+/g, "");
  if (!normalize(`${item.name} ${item.stock_code || ""}`).includes(normalize(query))) return false;
  const phase = ipoPhase(item, today);
  return filter === "all" || (filter === "active" ? phase !== "listed" && phase !== "withdrawn" : phase === filter);
}
