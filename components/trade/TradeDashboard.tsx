"use client";

import { useCallback, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowDownToLine, ArrowUpRight, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { signed, summarizeTrade, countryInfo, tradeRegions, tradeProducts, usdText, kgText, sortTradeCountries, percentagePoints, type TradeCountrySort, type TradeDataset, type TradeProduct } from "@/lib/trade";
import type { CompanyHistory } from "@/lib/trade-overlay";
import TradeTrend from "./TradeTrend";
import TradeUpdates from "./TradeUpdates";
import "./trade.css";

const TradeMap = dynamic(() => import("./TradeMap"), { ssr: false, loading: () => <div className="trade-map map-placeholder">지도 불러오는 중</div> });

export function TradeDashboard({ datasets, companies = [] }: { datasets: Record<string, TradeDataset | null>; companies?: CompanyHistory[] }) {
  const [productId, setProductId] = useState("dram");
  const product = tradeProducts.find(p => p.id === productId)!;
  const data = datasets[productId];
  return <main className="trade-page">
    <div className="trade-page-heading"><div className="trade-title-actions"><h1>수출 동향</h1><TradeUpdates onSelect={setProductId} /></div>
      <select aria-label="수출 품목" value={productId} onChange={e => setProductId(e.target.value)}>
        {tradeProducts.map(p => <option value={p.id} key={p.id}>{p.name} · {p.companies.map(c => c.name).join(" / ")}{p.id === "beauty" ? " 참고" : ""}</option>)}
      </select>
    </div>
    {data ? <TradeContent key={productId} data={data} product={product} companies={companies.filter(c => c.products.includes(productId))} /> : <div className="trade-empty">수집된 통계가 없습니다.</div>}
  </main>;
}

function TradeContent({ data, product, companies }: { data: TradeDataset; product: TradeProduct; companies: CompanyHistory[] }) {
  const months = useMemo(() => [...new Set(data.rows.map(r => r.month))].sort(), [data]);
  const [month, setMonth] = useState(months.at(-1)!);
  const [startMonth, setStartMonth] = useState(months.at(-1)!);
  const periodLabel = startMonth === month ? month.replace("-", ".") : `${startMonth.replace("-", ".")} ~ ${month.replace("-", ".")}`;
  const codes = useMemo(() => [...new Set(data.rows.filter(r => r.month >= startMonth && r.month <= month && r.usd > 0).map(r => r.country))], [data, startMonth, month]);
  const [country, setCountry] = useState("all");
  const [region, setRegion] = useState("all");
  const [countryQuery, setCountryQuery] = useState("");
  const [sort, setSort] = useState<{ key: TradeCountrySort; direction: "asc" | "desc" }>({ key: "usd", direction: "desc" });
  const onSelect = useCallback((code: string) => setCountry(code), []);
  const summary = useMemo(() => summarizeTrade(data, month, country, startMonth), [data, month, country, startMonth]);
  const mapCountries = useMemo(() => summarizeTrade(data, month, "all", startMonth).countries.filter(c => c.usd > 0), [data, month, startMonth]);
  const tableCountries = sortTradeCountries(mapCountries.filter(c => (region === "all" || c.region === region) && (c.name.toLowerCase().includes(countryQuery.toLowerCase()) || c.code.toLowerCase().includes(countryQuery.toLowerCase()))), sort.key, sort.direction);
  const countryName = country === "all" ? "전체 국가·지역 합계" : countryInfo(country).name;
  const sortHeader = (label: string, key: TradeCountrySort, basis?: string) => <th aria-sort={sort.key === key ? sort.direction === "asc" ? "ascending" : "descending" : "none"}><button onClick={() => setSort(current => ({ key, direction: current.key === key && current.direction === "desc" ? "asc" : "desc" }))}>{label}{sort.key === key ? sort.direction === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : <ArrowUpDown size={11} />}</button>{basis && <small>{basis}</small>}</th>;
  const exportCsv = () => {
    const rows = data.rows.filter(r => r.month >= startMonth && r.month <= month && (country === "all" || r.country === country));
    const csv = "\uFEFFscope,month,country,export_usd,net_weight_kg,usd_per_kg,hs_code\n" + rows.map(r => `${data.scope},${r.month},${r.country},${r.usd},${r.kg ?? ""},${r.kg ? r.usd / r.kg : ""},${data.hs}`).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${product.id}-${startMonth}-${month}.csv`;
    document.body.appendChild(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const signClass = (n: number | null) => n === null ? "" : n < 0 ? "trade-down" : n > 0 ? "trade-up" : "";
  return <>
    <div className="trade-toolbar">
      <div className="trade-subject"><h2>{product.name}</h2><span>HS {product.hs}</span></div>
      <div className="trade-selects">
        <div className="trade-date-range" role="group" aria-label="수출 집계 기간">
          <select aria-label="시작월" value={startMonth} onChange={e => { const next = e.target.value; setStartMonth(next); if (next > month) setMonth(next); setCountry("all"); setRegion("all"); }}>{months.slice().reverse().map(m => <option key={m} value={m}>{m.replace("-", ".")}</option>)}</select>
          <span aria-hidden="true">~</span>
          <select aria-label="종료월" value={month} onChange={e => { const next = e.target.value; setMonth(next); if (next < startMonth) setStartMonth(next); setCountry("all"); setRegion("all"); }}>{months.slice().reverse().map(m => <option key={m} value={m}>{m.replace("-", ".")}</option>)}</select>
        </div>
        <select aria-label="수출 대상국" value={country} onChange={e => { setCountry(e.target.value); setRegion("all"); }}><option value="all">전체 국가·지역</option>{codes.map(countryInfo).sort((a,b) => a.name.localeCompare(b.name, "ko")).map(c => <option value={c.code} key={c.code}>{c.name}</option>)}</select>
        <button className="trade-download" aria-label="CSV 다운로드" title="CSV 다운로드" onClick={exportCsv}><ArrowDownToLine size={16} /></button>
      </div>
    </div>
    <div className="trade-kpis">
      <div><span>{startMonth === month ? "월 수출금액" : "기간 수출금액"}</span><strong>{summary.now === null ? "자료 없음" : usdText(summary.now)}</strong><p>{periodLabel} · {countryName}</p></div>
      <div><span>전년 동기 대비</span><strong className={signClass(summary.yoy)}>{signed(summary.yoy)}</strong><p>{startMonth === month ? "전월 대비" : "직전 동일 길이 기간 대비"} <b className={signClass(summary.mom)}>{signed(summary.mom)}</b></p></div>
      <div><span>종료월 기준 최근 3개월</span><strong>{summary.recent === null ? "자료 없음" : usdText(summary.recent)}</strong><p>전년 동기 대비 <b className={signClass(summary.recentGrowth)}>{signed(summary.recentGrowth)}</b></p></div>
    </div>
    <div className="trade-weight-summary"><div><span>기간 수출 순중량</span><strong>{kgText(summary.kg)}</strong></div><div><span>kg당 수출액</span><strong>{summary.usdPerKg === null ? "자료 없음" : `${Math.round(summary.usdPerKg).toLocaleString("ko-KR")} 달러/kg`}</strong><p>수출금액 ÷ 순중량 · 제품 판매단가와 다릅니다.</p></div></div>
    <section className="trade-geography" aria-label="국가별 수출 지도">
      <div className="globe-filterbar"><select aria-label="대륙 필터" value={region} onChange={e => { setRegion(e.target.value); setCountry("all"); }}><option value="all">모든 대륙</option>{Object.entries(tradeRegions).filter(([key]) => mapCountries.some(c => c.region === key)).map(([key,name]) => <option key={key} value={key}>{name}</option>)}</select><span>{region === "all" ? mapCountries.length : mapCountries.filter(c => c.region === region).length}개 국가·지역</span>{country !== "all" && <button onClick={() => setCountry("all")}>전체 흐름</button>}</div>
      <TradeMap countries={mapCountries} selected={country} onSelect={onSelect} region={region} />
    </section>
    <div className="trade-analysis-grid">
      <TradeTrend chart={summary.chart} countryName={countryName} companies={companies} start={startMonth} end={month} />
      <section className="trade-country-table"><div className="section-heading"><h2>국가별 수출</h2><span className="unit-label">{periodLabel} · 달러</span></div>
        <input className="trade-country-search" aria-label="국가 검색" placeholder="국가명 또는 국가코드 검색" value={countryQuery} onChange={e => setCountryQuery(e.target.value)} />
        <div className="trade-table-scroll"><table><thead><tr><th>국가</th>{sortHeader("수출금액", "usd")}{sortHeader("순중량(kg)", "kg")}{sortHeader("달러/kg", "usdPerKg")}{sortHeader("YoY", "change", "선택 기간")}{sortHeader("MoM", "mom", month.replace("-", "."))}{sortHeader("비중", "share", "선택 기간")}{sortHeader("비중 변화", "shareChange", `${month.replace("-", ".")} 전월 대비`)}</tr></thead>
          <tbody>{tableCountries.map(c => <tr key={c.code} className={country === c.code ? "selected" : ""}>
            <td><button aria-pressed={country === c.code} onClick={() => setCountry(country === c.code ? "all" : c.code)}>{c.name}</button></td>
            <td>{usdText(c.usd).replace(" 달러", "")}</td><td>{c.kg === null ? "—" : Math.round(c.kg).toLocaleString("ko-KR")}</td><td>{c.usdPerKg === null ? "—" : Math.round(c.usdPerKg).toLocaleString("ko-KR")}</td><td className={signClass(c.change)}>{signed(c.change)}</td><td className={signClass(c.mom)}>{signed(c.mom)}</td>
            <td>{c.share === null ? "—" : c.share > 0 && c.share < 1 ? "1% 미만" : Math.round(c.share) + "%"}</td>
            <td className={signClass(c.shareChange)}>{percentagePoints(c.shareChange)}</td>
          </tr>)}</tbody></table>{!tableCountries.length && <p className="trade-no-results">검색 결과가 없습니다.</p>}</div>
      </section>
    </div>
    <div className="trade-related"><span>관련 기업</span>{product.companies.map(c => c.id ? <Link key={c.name} href={`/value-chain?company=${c.id}`}>{c.name}<ArrowUpRight size={12} /></Link> : <span key={c.name} className="trade-related-name">{c.name}</span>)}</div>
    <details className="trade-method"><summary>출처·집계 기준</summary>
      <p>관세청 월별 수출신고 미화금액(FOB). 시작월부터 종료월까지 합산하며, 전년 동기는 같은 월 범위를 1년 전과 비교합니다. 비중은 선택 기간 전체 품목 수출액 기준입니다. 모든 대상국 합계와 공식 총계가 일치한 월만 사용합니다. 기간 중 일부 월에 국가 행이 없으면 확인된 수출 신고액만 합산하며, 기간 전체에 응답이 없는 국가나 비교 기간이 누락된 경우는 자료 없음으로 처리합니다. 통계는 사후 정정될 수 있습니다.</p>
      <p>순중량은 관세청 expWgt(kg), 금액은 expDlr(FOB 달러)입니다. kg당 수출액은 합산 금액을 합산 중량으로 나눈 값이며 국가별 단가의 단순 평균이 아닙니다. 중량이 0이거나 없으면 계산하지 않습니다. 국가별 정수 kg 반올림으로 총계와 미세한 차이가 날 수 있어 전체 중량은 공식 총계를 사용합니다.</p>
      <p>표의 MoM과 비중 변화는 선택 종료월과 직전 월을 비교합니다. 비중 변화는 두 달의 국가별 수출 비중 차이(%p)이며, 기간 전체의 비중과 구분됩니다. 비교 월 누락이나 전월 수출액 0인 경우 MoM은 계산하지 않습니다.</p>
      <p>기업 오버레이는 전체 기업의 연결 실적이며 선택 국가만의 매출이 아닙니다. Q1~Q3는 단독 3개월 금액, Q4는 연간 금액에서 3분기 누적 금액을 차감합니다. 분기 말 위치는 공시 시점이 아니며 차트 상세에 공시일을 표시합니다. 축이 다른 선의 모양만으로 상관관계나 인과관계를 단정할 수 없습니다. 주가는 배당·분할 등을 보정하지 않은 월말 종가입니다.</p>
      <p>기업 데이터 출처: <a href="https://openapi.krx.co.kr/" target="_blank" rel="noreferrer">KRX 월말 거래일 종가</a> · <a href="https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020" target="_blank" rel="noreferrer">DART 연결 재무제표</a></p>
      <p>수출 대상국은 최종 소비국과 다를 수 있습니다. kg당 수출액에는 제품 구성·포장 제외 순중량·수출 대상국 구성 변화가 섞이며, D램 칩 개당 가격이나 기업의 실제 판매단가·실적을 의미하지 않습니다. 화면 숫자는 반올림하며 CSV에는 원자료를 보존합니다.</p>
      {product.id === "beauty" && <p>파마리서치 추적에 쓰이는 강릉시 HS 3304.99.9000과 구분됩니다. 현재 연결된 것은 전국 품목의 대상국별 통계로, 강릉시 자료는 미연결입니다. <a href="https://bbn.kiwoom.com/rfCR11799" target="_blank" rel="noreferrer">품목·지역 근거: 키움증권 리포트 4쪽</a></p>}
      {product.id === "transformer" && <p>HS 8504.23.0000: 용량 10,000kVA 초과 액체절연 변압기. 국내 전체 수출이며 개별 기업 매출과는 다릅니다. <a href="https://securities.miraeasset.com/bbs/download/2123974.pdf?attachmentId=2123974" target="_blank" rel="noreferrer">미래에셋증권 품목 분석</a></p>}
      <p><a href={data.source} target="_blank" rel="noreferrer">관세청 품목별 국가별 수출입실적</a>{data.retrievedAt && <span> · 조회일 {data.retrievedAt.slice(0, 10)}</span>}</p>
    </details>
  </>;
}
