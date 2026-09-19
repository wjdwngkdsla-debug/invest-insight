export type ObservedPoint = { date: string; value: number };
export type PeriodMetric = {
  searchIndex: ObservedPoint[];
  tradingValueIndex: ObservedPoint[];
  returnPct: number | null;
  currentPrice?: number | null;
  marketSource?: string;
  coverage?: { complete: boolean; from: string | null; to: string | null; observations: number };
};

export function observedPoints(points?: ObservedPoint[]) {
  return (points ?? []).filter(point => /^\d{4}-\d{2}-\d{2}$/.test(point.date) && Number.isFinite(Date.parse(point.date)) && Number.isFinite(point.value));
}

export function observedSum(points?: ObservedPoint[]): number | null {
  const values = observedPoints(points);
  return values.length ? values.reduce((sum, point) => sum + point.value, 0) : null;
}

export function observedAverage(points?: ObservedPoint[]): number | null {
  const values = observedPoints(points);
  return values.length ? values.reduce((sum, point) => sum + point.value, 0) / values.length : null;
}

export function observedReturn(metric?: PeriodMetric): number | null {
  return metric?.marketSource === "KRX" && metric.coverage?.complete && Number.isFinite(metric.returnPct)
    ? metric.returnPct : null;
}

export function observedPrice(metric?: PeriodMetric): number | null {
  return metric?.marketSource === "KRX" && typeof metric.currentPrice === "number" && metric.currentPrice > 0 ? metric.currentPrice : null;
}
