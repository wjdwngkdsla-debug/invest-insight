import { fetchEcosStat } from "./ecos";

export interface FxPoint {
  date: string; // YYYY-MM-DD
  rate: number;
}

// 주요국 통화의 대원화환율(731Y001) 품목코드
export const FX_ITEM_CODES = {
  USD: "0000001", // 원/미국달러
  JPY: "0000002", // 원/일본엔(100엔)
  EUR: "0000003", // 원/유로
  CNY: "0000053", // 원/위안
} as const;

export async function fetchFxDaily(
  itemCode: string,
  startPeriod: string,
  endPeriod: string
): Promise<FxPoint[]> {
  const rows = await fetchEcosStat({
    statCode: "731Y001",
    itemCode1: itemCode,
    cycle: "D",
    startPeriod,
    endPeriod,
    count: 1000,
  });

  return rows.map((r) => ({
    date: `${r.TIME.slice(0, 4)}-${r.TIME.slice(4, 6)}-${r.TIME.slice(6, 8)}`,
    rate: Number(r.DATA_VALUE),
  }));
}

// 원/달러 매매기준율 (일별) — 하위 호환용
export async function fetchUsdKrwDaily(startPeriod: string, endPeriod: string): Promise<FxPoint[]> {
  return fetchFxDaily(FX_ITEM_CODES.USD, startPeriod, endPeriod);
}
