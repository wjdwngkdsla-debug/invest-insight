export type CountryCode = "US" | "KR" | "JP" | "EU" | "CN" | "GB" | "IN" | "BR";

export interface TimeSeriesPoint {
  period: string; // e.g. "2025Q3"
  value: number | null;
  isEstimate?: boolean;
}

export interface CountrySeries {
  country: CountryCode;
  label: string;
  flag: string;
  charted: boolean; // true = 상단 차트에 표시되는 5개국
  series: TimeSeriesPoint[]; // 최근 10분기 + 추정치 1개 (charted가 true인 경우)
  current: number | null;
  currentPeriod?: string; // 현재값의 기준월/기준분기 (예: "2026-05")
  lastChangeDate?: string;
  nextAnnouncementDate?: string;
}

export interface DualAxisPoint {
  period: string;
  left: number | null;
  right: number | null;
  right2?: number | null;
}

export interface DualAxisSeries {
  title: string;
  leftLabel: string;
  rightLabel: string;
  data: DualAxisPoint[];
  correlation?: number;
  leftColor?: string;
  rightColor?: string;
  right2Label?: string; // 있으면 오른쪽 축에 보조 라인을 하나 더 그린다
  right2Color?: string;
}
