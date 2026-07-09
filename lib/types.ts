export type EventStatus = "예정" | "확정(경과)" | "반환확인" | "반환확인_API수정" | "수동확인" | "수동/API불일치";
export type LockupSource = "DART" | "투자설명서" | "공공데이터포털" | "수동입력";

export interface LockupEvent {
  period: string;
  date: string;
  date_display: string;
  tradable_date: string;
  qty: number;
  pct: number;
  type: "IPO확약" | "보호예수";
  status: EventStatus;
  source?: LockupSource;
  source_label?: string;
  rcp?: string;
  api_checked?: boolean;
  api_return_date?: string | null;
  api_return_qty?: number | null;
  api_source?: string;
  holder_name?: string | null;
  reason?: string | null;
  lockup_reg_date?: string | null;
}

export interface LockupHolder {
  category: string;
  holder_name: string;
  relation?: string;
  shares_after_ipo?: number;
  locked_qty: number;
  free_float_qty?: number;
  lockup_period: string;
  release_date: string;
  tradable_date: string;
  reason?: string;
  source: LockupSource;
}

export interface StockLockup {
  code: string;
  name: string;
  market: "코스피" | "코스닥";
  listing_date: string;
  shares: number;
  close_price: number;
  ipo_price?: number; // 확정 공모가(원). 0 또는 없음 = 미확인
  events: LockupEvent[];
  holders?: LockupHolder[];
}

export interface SiteData {
  updated: string;
  stocks: StockLockup[];
}
