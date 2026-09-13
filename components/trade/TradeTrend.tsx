"use client";

import { useMemo, useState } from "react";
import { kgText, usdText, chartMonthChanges, chartChangeText, type summarizeTrade } from "@/lib/trade";
import { overlayMetricNames, overlayPoints, type CompanyHistory, type OverlayMetric } from "@/lib/trade-overlay";

type Metric = "value" | "kg" | "usdPerKg";
type Point = ReturnType<typeof summarizeTrade>["chart"][number];
const colors = ["#208b80", "#bf6a31"];
export default function TradeTrend({ chart: history, countryName, companies, start, end }: {
  chart: Point[]; countryName: string; companies: CompanyHistory[]; start: string; end: string;
}) {
  const [metric, setMetric] = useState<Metric>("value");
  const [overlay, setOverlay] = useState<OverlayMetric>("none");
  const [companyIds, setCompanyIds] = useState(companies.map(c => c.id));
  const [range, setRange] = useState(24);
  const [active, setActive] = useState<string | null>(null);
  const [showChanges, setShowChanges] = useState(true);
  const chart = history.slice(-range);
  const changes = useMemo(() => chartMonthChanges(history, metric), [history, metric]);
  const months = useMemo(() => chart.map(p => p.month), [chart]);
  const peak = Math.max(1, ...chart.map(p => p[metric] ?? 0));
  const divisor = metric === "value" ? peak >= 1e8 ? 1e8 : peak >= 1e4 ? 1e4 : 1 : metric === "kg" && peak >= 1e4 ? 1e4 : 1;
  const unit = metric === "value" ? `${divisor === 1e8 ? "억 " : divisor === 1e4 ? "만 " : ""}달러` : metric === "kg" ? `${divisor === 1e4 ? "만 " : ""}kg` : "달러/kg";
  const metricName = metric === "value" ? "수출금액" : metric === "kg" ? "순중량" : "kg당 수출액";
  const format = (value: number | null) => value === null ? "자료 없음" : metric === "value" ? usdText(value) : metric === "kg" ? kgText(value) : `${Math.round(value).toLocaleString("ko-KR")} 달러/kg`;
  const available = (company: CompanyHistory, key: OverlayMetric) => overlayPoints(company, key, months).some(p => p.value !== null);
  const series = companies.filter(c => companyIds.includes(c.id) && available(c, overlay)).map(c => ({
    company: c, color: colors[companies.indexOf(c) % colors.length], points: overlayPoints(c, overlay, months),
  }));
  const values = series.flatMap(s => s.points.flatMap(p => p.value === null ? [] : [p.value]));
  const low = Math.min(0, ...values), high = Math.max(1, ...values);
  const rightMin = low < 0 ? low - (high - low) * .05 : 0, rightMax = high * 1.05;
  const x = (i: number) => (i + .5) / chart.length * 1000;
  const y = (value: number) => 220 - (value - rightMin) / (rightMax - rightMin) * 210;
  const activePoint = chart.find(p => p.month === active) ?? chart.at(-1);
  const rightUnit = overlay === "price" ? "원" : "억 원";
  const path = (points: ReturnType<typeof overlayPoints>) => {
    let previous = -Infinity;
    return points.flatMap((point, i) => {
      if (point.value === null) return [];
      const command = i - previous === (overlay === "price" ? 1 : 3) ? "L" : "M";
      previous = i;
      return [`${command}${x(i)},${y(point.value)}`];
    }).join(" ");
  };
  return <section className="trade-trend">
    <div className="section-heading"><div><h2>월별 수출 추이</h2><p data-testid="trend-country">{countryName}</p></div><div className="segmented">{[12, 24].map(n => <button key={n} aria-pressed={range === n} className={range === n ? "active" : ""} onClick={() => setRange(n)}>{n}개월</button>)}</div></div>
    <div className="trend-options">
      <select aria-label="차트 지표" value={metric} onChange={e => setMetric(e.target.value as Metric)}><option value="value">수출금액</option><option value="kg">순중량</option><option value="usdPerKg">kg당 수출액</option></select>
      <select aria-label="기업 비교 지표" value={overlay} onChange={e => setOverlay(e.target.value as OverlayMetric)}>{(Object.keys(overlayMetricNames) as OverlayMetric[]).map(key => <option key={key} value={key} disabled={key !== "none" && !companies.some(c => available(c, key))}>{overlayMetricNames[key]}{key !== "none" && !companies.some(c => available(c, key)) ? " · 자료 없음" : ""}</option>)}</select>
      <label className="trend-change-toggle"><input type="checkbox" checked={showChanges} onChange={e => setShowChanges(e.target.checked)} />전월 대비 (%)</label>
    </div>
    {overlay !== "none" && <div className="trend-company-options" role="group" aria-label="비교 기업">{companies.map((c, index) => <label key={c.id} style={{ color: colors[index % colors.length] }}><input type="checkbox" checked={companyIds.includes(c.id)} disabled={!available(c, overlay)} onChange={() => setCompanyIds(ids => ids.includes(c.id) ? ids.filter(id => id !== c.id) : [...ids, c.id])} />{c.name}{!available(c, overlay) && " (자료 없음)"}</label>)}</div>}
    <div className="trend-axis-head"><span>{metricName} · {unit}</span>{overlay !== "none" && <span>{overlayMetricNames[overlay]} · {rightUnit}</span>}</div>
    <div className="trade-overlay-chart" data-country={countryName}>
      {[0, 1, 2, 3].map(n => <div key={n} className="trend-grid" style={{ bottom: `${n / 3 * 210 + 10}px` }}><span className="trend-left-tick">{Math.round(peak / divisor * n / 3).toLocaleString("ko-KR")}</span>{overlay !== "none" && <span className="trend-right-tick">{Math.round(rightMin + (rightMax - rightMin) * n / 3).toLocaleString("ko-KR")}</span>}</div>)}
      <svg viewBox="0 0 1000 230" preserveAspectRatio="none" aria-hidden="true">
        {chart.map((p, i) => p[metric] !== null && <rect key={p.month} x={x(i) - 340 / chart.length} y={220 - p[metric]! / peak * 210} width={680 / chart.length} height={p[metric]! / peak * 210} fill={p.month >= start && p.month <= end ? "#637fe0" : "#b7c6ec"} />)}
        {series.map(s => <g key={s.company.id} data-overlay-series={s.company.id}><path d={path(s.points)} stroke={s.color} strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" />{s.points.map((p, i) => p.value !== null && <circle key={p.month} cx={x(i)} cy={y(p.value)} r="4" fill={s.color} data-overlay-value={p.value} />)}</g>)}
      </svg>
      {showChanges && <div className="trend-mom-layer" data-range={range} aria-hidden="true">{chart.map((p, i) => {
        const change = changes.get(p.month) ?? null;
        if (p[metric] === null || change === null) return null;
        return <span key={p.month} className={`trend-mom-point${p.month === activePoint?.month ? " is-active" : ""}`} data-month={p.month} data-change={change} style={{ left: `${(i + .5) / chart.length * 100}%`, top: `${220 - p[metric]! / peak * 210}px`, color: change > 0 ? "#b54d48" : change < 0 ? "#326db4" : "#687687" }}><i /><span className="trend-mom-label">{chartChangeText(change)}</span></span>;
      })}</div>}
      <div className="trend-hit-targets">{chart.map(p => <button key={p.month} data-export-value={p[metric] ?? ""} aria-label={`${p.month}, ${countryName}, ${metricName} ${format(p[metric])}, 전월 대비 ${chartChangeText(changes.get(p.month) ?? null)}`} onMouseEnter={() => setActive(p.month)} onFocus={() => setActive(p.month)} onClick={() => setActive(p.month)} />)}</div>
      <div className="trend-months">{chart.map((p, i) => <span key={p.month}>{(i % (range === 24 ? 4 : 2) === 0 && i < chart.length - 2) || i === chart.length - 1 ? p.month.slice(2).replace("-", ".") : ""}</span>)}</div>
    </div>
    <div className="trend-readout" aria-live="polite"><strong>{activePoint?.month.replace("-", ".")} · {countryName}</strong><span>{metricName} {format(activePoint?.[metric] ?? null)}</span><span className="trend-change-readout">전월 대비 {chartChangeText(changes.get(activePoint?.month ?? "") ?? null)}</span>{series.map(s => {
      const point = s.points.find(p => p.month === activePoint?.month);
      return <span key={s.company.id} style={{ color: s.color }}>{s.company.name} · {point?.value === null || point?.value === undefined ? overlay === "price" ? "자료 없음" : "분기 말에 표시" : `${point.label} ${Math.round(point.value).toLocaleString("ko-KR")} ${rightUnit}`}{point?.filedAt && ` · 공시 ${point.filedAt}`}</span>;
    })}</div>
    {overlay !== "none" && <p className="trend-basis">{overlay === "price" ? "월말 거래일 종가 · 수정주가 아님" : "연결 기준 단독 분기 실적 · 분기 말에 배치 (공시는 이후)"} · 좌우 축 단위가 다릅니다.</p>}
  </section>;
}
