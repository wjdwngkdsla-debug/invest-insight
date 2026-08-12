export type EventStatus = "예정" | "확정(경과)" | "반환확인" | "반환확인_API수정" | "수동확인" | "수동/API불일치";
export type LockupSource = "DART" | "투자설명서" | "공공데이터포털" | "수동입력";

export interface LockupEvent {
  period: string;
  date: string;
  date_display: string;
  tradable_date: string;
  qty: number;
  unit?: "주" | "DR";
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
  /** 같은 날 해제분의 주체별 물량 (최대주주·벤처금융·주식매수선택권 등) */
  reason_breakdown?: ReasonShare[];
  /** 해제일 당일 종가 */
  release_close?: number;
  /** 해제일 당일 등락률(%) — 거래소 FLUC_RT */
  release_fluc_rt?: number;
  lockup_reg_date?: string | null;
}

export interface ReasonShare {
  reason: string;
  qty: number;
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
  shares: number; // 최근 상장주식수(KRX) — 비율·종가 시가총액 기준
  initial_shares?: number; // 상장 시점 주식수 — 공모가 기준 시가총액 산출용
  listing_close?: number; // 상장일 종가(KRX 상장일 스냅샷). 공모가 대비 시초 성과 계산용
  close_price: number;
  trading_suspended?: boolean; // KRX 종목기본정보에는 있으나 당일 시세에서 빠진 거래정지 종목
  trading_suspended_since?: string; // 최초 거래정지 감지일(YYYY-MM-DD). 재개 전까지 유지
  market_cap?: number;
  ipo_price?: number; // 확정 공모가(원). 0 또는 없음 = 미확인
  adjusted_ipo_price?: number; // 기업행사 반영 현재 수익률 계산용 공모가. 화면의 원 공모가는 바꾸지 않는다.
  ipo_adjustment_factor?: number;
  ipo_adjustment_checked_at?: string;
  content_url?: string; // 종목 분석 포스팅 링크(종목관리 탭 입력). 없으면 기본 블로그
  events: LockupEvent[];
  holders?: LockupHolder[];
}

export interface SiteData {
  updated: string;
  shares_updated?: string;
  stocks: StockLockup[];
}
