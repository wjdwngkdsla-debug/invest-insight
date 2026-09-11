import countryMetadata from "../data/trade/countries.json" with { type: "json" };
export type TradeCountry = { code: string; name: string; lat: number | null; lon: number | null; region?: string };
export type TradeRow = { month: string; country: string; usd: number; kg?: number };
export type TradeDataset = { mode: "live"; source: string; hs: string; rows: TradeRow[]; countryCodes?: string[]; retrievedAt?: string; scope?: "all-countries" | "selected-countries"; monthlyTotals?: Record<string, number>; monthlyWeightTotals?: Record<string, number> };
export const tradeProducts = [
  { id: "dram", name: "D램", hs: "8542321010", companies: [{ name: "SK하이닉스", id: "skhynix" }, { name: "삼성전자", id: "samsung" }],
    note: "D램 칩 기준 · 개별 기업·HBM 매출과 다릅니다." },
  { id: "beauty", name: "기타 미용·기초화장품", hs: "3304999000", companies: [{ name: "파마리서치", id: "" }],
    note: "전국 품목 통계 · 강릉시·리쥬란 수출액이 아닙니다." },
] as const;
export type TradeProduct = (typeof tradeProducts)[number];

export const tradeCountries: TradeCountry[] = countryMetadata;
export const tradeRegions: Record<string, string> = { Asia: "아시아", Europe: "유럽", Americas: "아메리카", Africa: "아프리카", Oceania: "오세아니아", Antarctic: "남극", Other: "기타" };
export function countryInfo(code: string): TradeCountry {
  return tradeCountries.find(c => c.code === code) ?? { code, name: code === "AN" ? "네덜란드령 안틸레스(구 코드)" : code === "ZZ" ? "기타·미분류 지역" : code + " (기타 지역)", lat: null, lon: null, region: "Other" };
}

export function validTradeDataset(value: unknown, hs: string): value is TradeDataset {
  if (!value || typeof value !== "object") return false;
  const data = value as TradeDataset;
  if (data.mode !== "live" || data.hs !== hs || !Array.isArray(data.rows) || !data.rows.length) return false;
  if (data.rows.some(r => !r || !Number.isFinite(r.usd) || (r.kg !== undefined && (!Number.isFinite(r.kg) || r.kg < 0)))) return false;
  if (data.monthlyWeightTotals) {
    for (const [month, kg] of Object.entries(data.monthlyWeightTotals)) {
      const rows = data.rows.filter(r => r.month === month);
      if (!Number.isFinite(kg) || kg < 0 || !rows.length || rows.some(r => r.kg === undefined) ||
        Math.abs(rows.reduce((n, r) => n + r.kg!, 0) - kg) > (rows.length + 1) / 2) return false;
    }
    if (data.rows.some(r => data.monthlyWeightTotals?.[r.month] === undefined)) return false;
  }
  if (data.countryCodes !== undefined && (!Array.isArray(data.countryCodes) || !data.countryCodes.length ||
    new Set(data.countryCodes).size !== data.countryCodes.length ||
    data.countryCodes.some(code => !/^[A-Z0-9]{2}$/.test(code)))) return false;
  if (data.scope === "all-countries") {
    if (!data.monthlyTotals || !Object.keys(data.monthlyTotals).length) return false;
    for (const [month, total] of Object.entries(data.monthlyTotals)) {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month) || !Number.isFinite(total) || total < 0 ||
        data.rows.filter(r => r.month === month).reduce((n, r) => n + r.usd, 0) !== total) return false;
    }
    if (data.rows.some(r => data.monthlyTotals?.[r.month] === undefined)) return false;
  }
  const seen = new Set<string>();
  return data.rows.every(row => {
    if (!row || !/^\d{4}-(0[1-9]|1[0-2])$/.test(row.month) || !/^[A-Z0-9]{2}$/.test(row.country) || !Number.isFinite(row.usd) || row.usd < 0) return false;
    if (data.countryCodes && !data.countryCodes.includes(row.country)) return false;
    const key = `${row.month}:${row.country}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function priorMonth(month: string, offset: number) {
  const [year, m] = month.split("-").map(Number);
  return new Date(Date.UTC(year, m - 1 - offset, 1)).toISOString().slice(0, 7);
}
export function growth(current: number, prior: number): number | null {
  return prior > 0 ? (current / prior - 1) * 100 : null;
}
export function signed(value: number | null) {
  return value === null ? "비교자료 없음" : `${value > 0 ? "+" : ""}${Math.round(value)}%`;
}
export function usdText(value: number) {
  const amount = Math.round(Math.abs(value));
  const sign = value < 0 ? "-" : "";
  if (amount >= 1e8 - 5000) {
    const rounded = Math.round(amount / 1e4), rest = rounded % 10000;
    return `${sign}${Math.floor(rounded / 10000).toLocaleString("ko-KR")}억${rest ? ` ${rest.toLocaleString("ko-KR")}만` : ""} 달러`;
  }
  if (amount >= 1e4) return `${sign}${Math.round(amount / 1e4).toLocaleString("ko-KR")}만 달러`;
  return `${sign}${amount.toLocaleString("ko-KR")} 달러`;
}
export const kgText = (kg: number | null) => kg === null ? "자료 없음" : `${Math.round(kg).toLocaleString("ko-KR")} kg`;
export const unitValue = (usd: number | null, kg: number | null) => usd !== null && kg !== null && kg > 0 ? usd / kg : null;
export function summarizeTrade(data: TradeDataset, month: string, selected = "all") {
  const months = [...new Set(data.rows.map(r => r.month))].sort();
  const codes = data.countryCodes ?? [...new Set(data.rows.map(r => r.country))];
  const total = (m: string, country = selected): number | null => {
    const rows = data.rows.filter(r => r.month === m && (country === "all" || r.country === country));
    if (country === "all" && data.scope === "all-countries") return data.monthlyTotals?.[m] ?? null;
    if (country === "all" && codes.some(code => !rows.some(r => r.country === code))) return null;
    return rows.length ? rows.reduce((n, r) => n + r.usd, 0) : null;
  };
  const now = total(month);
  const weight = (m: string, country = selected): number | null => {
    if (country === "all" && data.monthlyWeightTotals) return data.monthlyWeightTotals[m] ?? null;
    const rows = data.rows.filter(r => r.month === m && (country === "all" || r.country === country));
    return rows.length && rows.every(r => r.kg !== undefined) ? rows.reduce((n, r) => n + r.kg!, 0) : null;
  };
  const kg = weight(month);
  const previous = total(priorMonth(month, 12));
  const lastMonth = total(priorMonth(month, 1));
  const sum3 = (m: string) => {
    const values = [0, 1, 2].map(offset => total(priorMonth(m, offset)));
    return values.every(v => v !== null) ? values.reduce<number>((a, b) => a + (b ?? 0), 0) : null;
  };
  const recent = sum3(month), prior = sum3(priorMonth(month, 12));
  const countries = codes.map(countryInfo).map(c => {
    const value = total(month, c.code), old = total(priorMonth(month, 12), c.code);
    return { ...c, usd: value ?? 0, kg: weight(month, c.code), usdPerKg: unitValue(value, weight(month, c.code)), available: value !== null,
      change: value !== null && old !== null ? growth(value, old) : null,
      delta: value !== null && old !== null ? value - old : null,
      share: (total(month, "all") ?? 0) > 0 ? (value ?? 0) / total(month, "all")! * 100 : null };
  }).filter(c => c.available).sort((a, b) => b.usd - a.usd);
  return { now, kg, usdPerKg: unitValue(now, kg), yoy: now !== null && previous !== null ? growth(now, previous) : null,
    mom: now !== null && lastMonth !== null ? growth(now, lastMonth) : null,
    recent, recentGrowth: recent !== null && prior !== null ? growth(recent, prior) : null,
    countries, chart: months.filter(m => m <= month).slice(-24).map(m => ({ month: m, value: total(m), kg: weight(m), usdPerKg: unitValue(total(m), weight(m)), previous: total(priorMonth(m, 12)) })) };
}
