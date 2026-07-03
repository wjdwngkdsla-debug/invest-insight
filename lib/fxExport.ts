import { fetchFxDaily, FX_ITEM_CODES } from "./fx";
import { fetchCustomsTradeTotal } from "./customs";
import { toEok } from "./format";
import { lastCompletedYymm, yymmMonthsAgo } from "./dateUtils";

export interface FxExportPoint {
  period: string; // YYYY-MM
  exportAmount: number; // 억 달러
  usdKrw: number; // 원/달러 월평균 실제값
  jpyKrw: number; // 원/100엔 월평균 실제값
  eurKrw: number; // 원/유로 월평균 실제값
  cnyKrw: number; // 원/위안 월평균 실제값
  usdPct: number; // 구간 시작월 대비 등락률(%)
  jpyPct: number;
  eurPct: number;
  cnyPct: number;
}

export interface FxExportSeries {
  title: string;
  data: FxExportPoint[];
}

// 환율(usdKrw 등)은 한국은행 원/달러(등) 매매기준율의 "일별 값을 월 단위로 평균"한 것이다.
// (예: usdKrw = 2026-05 원/달러 매매기준율 영업일 평균)
function monthlyAverage(points: { date: string; rate: number }[]): Map<string, number> {
  const byMonth = new Map<string, number[]>();
  for (const p of points) {
    const ym = p.date.slice(0, 7);
    const arr = byMonth.get(ym) ?? [];
    arr.push(p.rate);
    byMonth.set(ym, arr);
  }
  return new Map(
    Array.from(byMonth.entries()).map(([ym, vals]) => [ym, Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100])
  );
}

export async function fetchFxVsExport(): Promise<FxExportSeries> {
  const endYymm = lastCompletedYymm(); // 이번 달은 아직 미완결이라 제외
  const startYymm = yymmMonthsAgo(23, endYymm); // 최근 24개월
  const startDateStr = `${startYymm}01`;
  const endDateStr = `${endYymm}31`;

  const [trade, usd, jpy, eur, cny] = await Promise.all([
    fetchCustomsTradeTotal({ startYymm, endYymm }),
    fetchFxDaily(FX_ITEM_CODES.USD, startDateStr, endDateStr),
    fetchFxDaily(FX_ITEM_CODES.JPY, startDateStr, endDateStr),
    fetchFxDaily(FX_ITEM_CODES.EUR, startDateStr, endDateStr),
    fetchFxDaily(FX_ITEM_CODES.CNY, startDateStr, endDateStr),
  ]);

  const usdByMonth = monthlyAverage(usd);
  const jpyByMonth = monthlyAverage(jpy);
  const eurByMonth = monthlyAverage(eur);
  const cnyByMonth = monthlyAverage(cny);

  const rows: { period: string; exportAmount: number; usdKrw: number; jpyKrw: number; eurKrw: number; cnyKrw: number }[] = [];
  for (const t of trade) {
    const usdKrw = usdByMonth.get(t.period);
    const jpyKrw = jpyByMonth.get(t.period);
    const eurKrw = eurByMonth.get(t.period);
    const cnyKrw = cnyByMonth.get(t.period);
    if (usdKrw == null || jpyKrw == null || eurKrw == null || cnyKrw == null) continue;

    rows.push({ period: t.period, exportAmount: toEok(t.exportAmount), usdKrw, jpyKrw, eurKrw, cnyKrw });
  }

  const windowed = rows.slice(-24);
  const base = windowed[0];

  const pct = (cur: number, base: number) => Math.round(((cur - base) / base) * 10000) / 100;

  const data: FxExportPoint[] = windowed.map((r) => ({
    ...r,
    usdPct: base ? pct(r.usdKrw, base.usdKrw) : 0,
    jpyPct: base ? pct(r.jpyKrw, base.jpyKrw) : 0,
    eurPct: base ? pct(r.eurKrw, base.eurKrw) : 0,
    cnyPct: base ? pct(r.cnyKrw, base.cnyKrw) : 0,
  }));

  return {
    title: "전체 수출액(억 달러) ↔ 주요 통화 환율 등락률",
    data,
  };
}
