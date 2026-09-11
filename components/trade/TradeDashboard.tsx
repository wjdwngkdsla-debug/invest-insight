"use client";

import { useCallback, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowDownToLine, ArrowUpRight } from "lucide-react";
import { signed, summarizeTrade, countryInfo, tradeRegions, tradeProducts, usdText, kgText, type TradeDataset, type TradeProduct } from "@/lib/trade";
import "./trade.css";

const TradeMap = dynamic(() => import("./TradeMap"), { ssr: false, loading: () => <div className="trade-map map-placeholder">지도 불러오는 중</div> });

export function TradeDashboard({ datasets }: { datasets: Record<string, TradeDataset | null> }) {
  const [productId, setProductId] = useState("dram");
  const product = tradeProducts.find(p => p.id === productId)!;
  const data = datasets[productId];
  return <main className="trade-page">
    <div className="trade-page-heading"><h1>수출 동향</h1>
      <select aria-label="수출 품목" value={productId} onChange={e => setProductId(e.target.value)}>
        {tradeProducts.map(p => <option value={p.id} key={p.id}>{p.id === "dram" ? "D램 · SK하이닉스 / 삼성전자" : "미용·기초화장품 · 파마리서치 참고"}</option>)}
      </select>
    </div>
    {data ? <TradeContent key={productId} data={data} product={product} /> : <div className="trade-empty">수집된 통계가 없습니다.</div>}
  </main>;
}

function TradeContent({ data, product }: { data: TradeDataset; product: TradeProduct }) {
  const months = useMemo(() => [...new Set(data.rows.map(r => r.month))].sort(), [data]);
  const [month, setMonth] = useState(months.at(-1)!);
  const codes = useMemo(() => data.rows.filter(r => r.month === month && r.usd > 0).map(r => r.country), [data, month]);
  const [country, setCountry] = useState("all");
  const [region, setRegion] = useState("all");
  const [countryQuery, setCountryQuery] = useState("");
  const [chartRange, setChartRange] = useState(24);
  const [activePoint, setActivePoint] = useState<string | null>(null);
  const [metric, setMetric] = useState<"value" | "kg" | "usdPerKg">("value");
  const [sort, setSort] = useState<"usd" | "change" | "delta">("usd");
  const onSelect = useCallback((code: string) => setCountry(code), []);
  const summary = useMemo(() => summarizeTrade(data, month, country), [data, month, country]);
  const mapCountries = useMemo(() => summarizeTrade(data, month).countries.filter(c => c.usd > 0), [data, month]);
  const tableCountries = mapCountries.filter(c => (region === "all" || c.region === region) && (c.name.toLowerCase().includes(countryQuery.toLowerCase()) || c.code.toLowerCase().includes(countryQuery.toLowerCase()))).sort((a, b) => (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity));
  const countryName = country === "all" ? "전체 국가·지역 합계" : countryInfo(country).name;
  const chart = summary.chart.slice(-chartRange);
  const peak = Math.max(1, ...chart.map(p => p[metric] ?? 0));
  const axisDivisor = metric === "value" ? peak >= 1e8 ? 1e8 : peak >= 1e4 ? 1e4 : 1 : 1;
  const metricName = metric === "value" ? "수출금액" : metric === "kg" ? "순중량" : "kg당 수출액";
  const axisUnit = metric === "value" ? `${axisDivisor === 1e8 ? "억 " : axisDivisor === 1e4 ? "만 " : ""}달러` : metric === "kg" ? "kg" : "달러/kg";
  const metricText = (value: number | null) => value === null ? "자료 없음" : metric === "value" ? usdText(value) : metric === "kg" ? kgText(value) : `${Math.round(value).toLocaleString("ko-KR")} 달러/kg`;
  const selectedPoint = chart.find(p => p.month === activePoint);
  const exportCsv = () => {
    const rows = data.rows.filter(r => r.month <= month && (country === "all" || r.country === country));
    const csv = "\uFEFFscope,month,country,export_usd,net_weight_kg,usd_per_kg,hs_code\n" + rows.map(r => `${data.scope},${r.month},${r.country},${r.usd},${r.kg ?? ""},${r.kg ? r.usd / r.kg : ""},${data.hs}`).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${product.id}-${month}.csv`; link.click(); URL.revokeObjectURL(url);
  };
  const signClass = (n: number | null) => n === null ? "" : n < 0 ? "trade-down" : n > 0 ? "trade-up" : "";
  return <>
    <div className="trade-toolbar">
      <div className="trade-subject"><h2>{product.name}</h2><span>HS {product.hs}</span></div>
      <div className="trade-selects">
        <select aria-label="기준월" value={month} onChange={e => { const next = e.target.value; setMonth(next); setActivePoint(null); setRegion("all"); if (!data.rows.some(r => r.month === next && r.country === country && r.usd > 0)) setCountry("all"); }}>{months.slice().reverse().map(m => <option key={m} value={m}>{m.replace("-", ".")}</option>)}</select>
        <select aria-label="수출 대상국" value={country} onChange={e => { setCountry(e.target.value); setRegion("all"); }}><option value="all">전체 국가·지역</option>{codes.map(countryInfo).sort((a,b) => a.name.localeCompare(b.name, "ko")).map(c => <option value={c.code} key={c.code}>{c.name}</option>)}</select>
        <button className="trade-download" aria-label="CSV 다운로드" title="CSV 다운로드" onClick={exportCsv}><ArrowDownToLine size={16} /></button>
      </div>
    </div>
    <p className="trade-scope">{product.note} <span>해당 월 {mapCountries.length}개 국가·지역 · API 전체 총계 대조 완료</span></p>
    <div className="trade-kpis">
      <div><span>월 수출금액</span><strong>{summary.now === null ? "자료 없음" : usdText(summary.now)}</strong><p>{month.replace("-", ".")} · {countryName}</p></div>
      <div><span>전년 동월 대비</span><strong className={signClass(summary.yoy)}>{signed(summary.yoy)}</strong><p>전월 대비 <b className={signClass(summary.mom)}>{signed(summary.mom)}</b></p></div>
      <div><span>최근 3개월 합계</span><strong>{summary.recent === null ? "자료 없음" : usdText(summary.recent)}</strong><p>전년 동기 대비 <b className={signClass(summary.recentGrowth)}>{signed(summary.recentGrowth)}</b></p></div>
    </div>
    <div className="trade-weight-summary"><div><span>월 수출 순중량</span><strong>{kgText(summary.kg)}</strong></div><div><span>kg당 수출액</span><strong>{summary.usdPerKg === null ? "자료 없음" : `${Math.round(summary.usdPerKg).toLocaleString("ko-KR")} 달러/kg`}</strong><p>수출금액 ÷ 순중량 · 제품 판매단가와 다릅니다.</p></div></div>
    <section className="trade-geography" aria-label="국가별 수출 지도">
      <div className="globe-filterbar"><select aria-label="대륙 필터" value={region} onChange={e => { setRegion(e.target.value); setCountry("all"); }}><option value="all">모든 대륙</option>{Object.entries(tradeRegions).filter(([key]) => mapCountries.some(c => c.region === key)).map(([key,name]) => <option key={key} value={key}>{name}</option>)}</select><span>{region === "all" ? mapCountries.length : mapCountries.filter(c => c.region === region).length}개 국가·지역</span>{country !== "all" && <button onClick={() => setCountry("all")}>전체 흐름</button>}</div>
      <TradeMap countries={mapCountries} selected={country} onSelect={onSelect} region={region} />
    </section>
    <div className="trade-analysis-grid">
      <section className="trade-trend">
        <div className="section-heading"><div><h2>월별 수출 추이</h2><p>{countryName} · {axisUnit}</p></div><div className="segmented">{[12, 24].map(n => <button aria-pressed={chartRange === n} className={chartRange === n ? "active" : ""} onClick={() => setChartRange(n)} key={n}>{n}개월</button>)}</div></div>
        <select aria-label="차트 지표" value={metric} onChange={e => setMetric(e.target.value as typeof metric)}><option value="value">수출금액</option><option value="kg">순중량</option><option value="usdPerKg">kg당 수출액</option></select>
        <div className="trade-chart" onMouseLeave={() => setActivePoint(null)}>
          {[0, 1, 2, 3].map(n => <div className="chart-grid-line" key={n} style={{ bottom: `${n * 30 + 8}%` }}><span>{Math.round(peak / axisDivisor * n / 3).toLocaleString("ko-KR")}</span></div>)}
          <div className="chart-columns">{chart.map(p => <button key={p.month} className="chart-column" aria-label={`${p.month}, ${metricText(p[metric])}`} onFocus={() => setActivePoint(p.month)} onMouseEnter={() => setActivePoint(p.month)} onClick={() => setActivePoint(p.month)}>
            <span className="chart-bars"><i className="bar-current" style={{ height: `${(p[metric] ?? 0) / peak * 100}%` }} /></span>
            <span className="chart-month">{p.month.slice(2).replace("-", ".")}</span></button>)}</div>
          {selectedPoint && <div className="chart-tooltip"><strong>{selectedPoint.month}</strong><span>{metricName} {metricText(selectedPoint[metric])}</span></div>}
        </div>
      </section>
      <section className="trade-country-table"><div className="section-heading"><h2>국가별 수출</h2><span className="unit-label">{month.replace("-", ".")} · 달러</span></div>
        <input className="trade-country-search" aria-label="국가 검색" placeholder="국가명 또는 국가코드 검색" value={countryQuery} onChange={e => setCountryQuery(e.target.value)} />
        <div className="trade-table-scroll"><table><thead><tr><th>국가</th><th aria-sort={sort === "usd" ? "descending" : "none"}><button onClick={() => setSort("usd")}>수출금액 {sort === "usd" ? "↓" : ""}</button></th><th>순중량(kg)</th><th>달러/kg</th><th aria-sort={sort === "change" ? "descending" : "none"}><button onClick={() => setSort("change")}>전년 대비 {sort === "change" ? "↓" : ""}</button></th><th>비중</th></tr></thead>
          <tbody>{tableCountries.map(c => <tr key={c.code} className={country === c.code ? "selected" : ""}>
            <td><button aria-pressed={country === c.code} onClick={() => setCountry(country === c.code ? "all" : c.code)}>{c.name}</button></td>
            <td>{usdText(c.usd).replace(" 달러", "")}</td><td>{c.kg === null ? "—" : Math.round(c.kg).toLocaleString("ko-KR")}</td><td>{c.usdPerKg === null ? "—" : Math.round(c.usdPerKg).toLocaleString("ko-KR")}</td><td className={signClass(c.change)}>{signed(c.change)}</td>
            <td>{c.share === null ? "—" : c.share > 0 && c.share < 1 ? "1% 미만" : Math.round(c.share) + "%"}</td>
          </tr>)}</tbody></table>{!tableCountries.length && <p className="trade-no-results">검색 결과가 없습니다.</p>}</div>
      </section>
    </div>
    <div className="trade-related"><span>관련 기업</span>{product.companies.map(c => c.id ? <Link key={c.name} href={`/value-chain?company=${c.id}`}>{c.name}<ArrowUpRight size={12} /></Link> : <span key={c.name} className="trade-related-name">{c.name}</span>)}</div>
    <details className="trade-method"><summary>출처·집계 기준</summary>
      <p>관세청 월별 수출신고 미화금액(FOB). 국가 조건 없이 해당 품목의 모든 국가·지역을 조회하고, 국가별 합계를 API 총계와 대조했습니다. 비중은 해당 월 전체 품목 수출액 기준이며 대륙 필터로 분모가 바뀌지 않습니다. 해당 월에 응답이 없는 국가는 0으로 추정하지 않습니다. 통계는 사후 정정될 수 있습니다.</p>
      <p>순중량은 관세청 expWgt(kg), 금액은 expDlr(FOB 달러)입니다. kg당 수출액은 합산 금액을 합산 중량으로 나눈 값이며 국가별 단가의 단순 평균이 아닙니다. 중량이 0이거나 없으면 계산하지 않습니다. 국가별 정수 kg 반올림으로 총계와 미세한 차이가 날 수 있어 전체 중량은 공식 총계를 사용합니다.</p>
      <p>수출 대상국은 최종 소비국과 다를 수 있습니다. kg당 수출액에는 제품 구성·포장 제외 순중량·수출 대상국 구성 변화가 섞이며, D램 칩 개당 가격이나 기업의 실제 판매단가·실적을 의미하지 않습니다. 화면 숫자는 반올림하며 CSV에는 원자료를 보존합니다.</p>
      {product.id === "beauty" && <p>파마리서치 추적에 쓰이는 강릉시 HS 3304.99.9000과 구분됩니다. 현재 연결된 것은 전국 품목의 대상국별 통계로, 강릉시 자료는 미연결입니다. <a href="https://bbn.kiwoom.com/rfCR11799" target="_blank" rel="noreferrer">품목·지역 근거: 키움증권 리포트 4쪽</a></p>}
      <p><a href={data.source} target="_blank" rel="noreferrer">관세청 품목별 국가별 수출입실적</a>{data.retrievedAt && <span> · 조회일 {data.retrievedAt.slice(0, 10)}</span>}</p>
    </details>
  </>;
}
