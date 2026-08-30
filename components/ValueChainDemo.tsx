"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import {
  getCompanyFinancial,
  getIssueMetricCache,
  issueCompositeScore,
  semiconductorCompanies,
  semiconductorTopics,
  topMarketIssues,
  type CompanyRegion,
  type ValueChainCompany,
  type ValueChainCompanyMetricCache,
  type ValueChainDataStatus,
  type ValueChainIssueScore,
} from "@/lib/valueChain";

type Metric = "search" | "volume" | "return";
type Period = "day" | "week" | "month" | "quarter" | "half";
type ViewMode = "map" | "returns";
type OrbitCategory = "산업" | "섹터" | "관련주" | "이슈";

interface Company {
  id: string;
  name: string;
  role: string;
  detail: string;
  critical?: string;
  score: number;
  returnPct: number;
  marketCap: number;
  sales: number;
  op: number;
  quarterSales: number;
  quarterOp: number;
  metric?: ValueChainCompanyMetricCache;
  financialStatus?: ValueChainDataStatus;
  financialAsOf?: string;
  region: CompanyRegion;
}

interface Issue {
  id: string;
  title: string;
  category: string;
  desc: string;
  companyIds: string[];
  composite: number;
  searchChg: number;
  volumeChg: number;
  returnChg: number;
}

interface OrbitCenter {
  title: string;
  category: OrbitCategory;
  subtitle: string;
}

interface OrbitItem {
  id: string;
  type: "company" | "issue";
  name: string;
  role: string;
  detail: string;
  score: number;
  category: OrbitCategory;
  critical?: string;
}

interface NavState {
  selectedId: string;
  focusCompanyId: string | null;
}

interface SearchResult {
  id: string;
  type: "issue" | "company";
  title: string;
  category: OrbitCategory;
  desc: string;
  countText: string;
}

const TAU = Math.PI * 2;
const CHART_COLORS = ["#60a5fa", "#a78bfa", "#34d399", "#fb923c", "#f472b6", "#38bdf8"];
const DEFAULT_DETAIL_PANEL_WIDTH = 980;
const MIN_DETAIL_PANEL_WIDTH = 560;
const MAX_DETAIL_PANEL_WIDTH = 1180;
const PERIOD_OPTIONS: Array<{ value: Period; label: string }> = [
  { value: "day", label: "1일" },
  { value: "week", label: "1주일" },
  { value: "month", label: "1개월" },
  { value: "quarter", label: "3개월" },
  { value: "half", label: "6개월" },
];

function scoreCompany(company: ValueChainCompany) {
  const returnScore = company.oneYearReturn ? Math.min(Math.max(company.oneYearReturn, -30), 80) : 0;
  const criticalBonus = company.critical === "독점" ? 12 : company.critical === "핵심" ? 8 : 0;
  const listedBonus = company.listing === "listed" ? 5 : 0;
  return Math.round(Math.min(99, Math.max(45, 58 + returnScore * 0.35 + criticalBonus + listedBonus)));
}

function toDemoCompany(company: ValueChainCompany): Company {
  const financial = getCompanyFinancial(company.id);
  return {
    id: company.id,
    name: company.name,
    role: company.role,
    detail: company.roleDetail || company.verificationNote || `${company.name}은 ${company.role} 영역과 연결된 기업입니다.`,
    critical: company.critical,
    score: scoreCompany(company),
    returnPct: company.oneYearReturn ?? 0,
    marketCap: financial?.marketCap ?? company.marketCap ?? 0,
    sales: financial?.annual.sales.at(-1) ?? company.sales.at(-1) ?? 0,
    op: financial?.annual.operatingProfit.at(-1) ?? company.operatingProfit.at(-1) ?? 0,
    quarterSales: financial?.recentQuarter.sales ?? 0,
    quarterOp: financial?.recentQuarter.operatingProfit ?? 0,
    financialStatus: financial?.status,
    financialAsOf: financial?.asOf,
    region: company.region,
  };
}

function toDemoIssue(issue: ValueChainIssueScore): Issue {
  return {
    id: issue.id,
    title: issue.title,
    category: issue.category,
    desc: issue.description,
    companyIds: issue.companyIds,
    composite: issueCompositeScore(issue),
    searchChg: issue.searchChangePct,
    volumeChg: issue.volumeChangePct,
    returnChg: issue.avgReturnPct,
  };
}

const VALUE_CHAIN_COMPANIES: Record<string, Company> = Object.fromEntries(
  semiconductorCompanies.map((company) => [company.id, toDemoCompany(company)]),
);

const VALUE_CHAIN_ISSUES: Issue[] = topMarketIssues.map(toDemoIssue);
const VALUE_CHAIN_TOPIC_ISSUES: Issue[] = semiconductorTopics
  .filter((topic) => topic.kind !== "hub" && topic.companyIds.length)
  .map((topic) => ({
    id: `topic-${topic.id}`,
    title: topic.title,
    category: topic.layerType === "industry" ? "산업" : "섹터",
    desc: topic.description || topic.note,
    companyIds: topic.companyIds,
    composite: 0,
    searchChg: 0,
    volumeChg: 0,
    returnChg: 0,
  }));
const VALUE_CHAIN_NAV_ISSUES = [...VALUE_CHAIN_ISSUES, ...VALUE_CHAIN_TOPIC_ISSUES];

function issuePeriodReturns(issue: Issue, period: Period) {
  const metric = getIssueMetricCache(issue.id);
  const values = (metric?.companies || [])
    .filter((company) => VALUE_CHAIN_COMPANIES[company.companyId]?.region === "domestic")
    .map((company) => company[period]?.returnPct)
    .filter((value): value is number => Number.isFinite(value));
  if (values.length) return values;
  return issue.companyIds
    .map((id) => VALUE_CHAIN_COMPANIES[id])
    .filter((company): company is Company => Boolean(company) && company.region === "domestic")
    .map((company) => company.returnPct)
    .filter((value): value is number => Number.isFinite(value))
    .map((value) => periodReturn(value, period));
}

function domesticIssueCompanies(issue: Issue) {
  return issue.companyIds.filter((id) => VALUE_CHAIN_COMPANIES[id]?.region === "domestic");
}

function issueAverageReturn(issue: Issue, period: Period) {
  const values = issuePeriodReturns(issue, period);
  if (!values.length) return null;
  return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10;
}

function issueReturnCount(issue: Issue, period: Period) {
  return issuePeriodReturns(issue, period).length;
}

function generateSeries(issue: Issue, company: Company, metric: Metric, period: Period, index: number) {
  const length = period === "day" ? 2 : period === "week" ? 7 : period === "month" ? 5 : period === "quarter" ? 13 : 6;
  const periodScale =
    period === "half" ? 2.4 : period === "quarter" ? 2 : period === "month" ? (metric === "volume" ? 2.15 : metric === "search" ? 1.85 : 1.45) : period === "day" ? 0.28 : 1;
  const base =
    metric === "return"
      ? company.returnPct * 0.42
      : metric === "search"
        ? issue.searchChg * (1 - index * 0.09)
        : issue.volumeChg * (1 - index * 0.08);
  return Array.from({ length }, (_, pointIndex) => {
    const progress = length > 1 ? pointIndex / (length - 1) : 1;
    const wave = Math.sin((pointIndex + 1) * (index + 1) * 0.72) * (period === "week" ? 4 : 9);
    const curve = period === "month" ? progress ** 1.15 : progress;
    return Math.round((base * 0.22 + base * 0.78 * curve + wave) * periodScale * 10) / 10;
  });
}

function fmtWon(value: number) {
  if (!value) return "-";
  if (value < 10000) return `${value.toLocaleString()}억`;
  const jo = Math.floor(value / 10000);
  const eok = Math.round(value % 10000);
  return eok ? `${jo.toLocaleString()}조 ${eok.toLocaleString()}억` : `${jo.toLocaleString()}조`;
}

function fmtPct(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function periodReturn(value: number, period: Period) {
  if (period === "day") return Math.round(value * 0.18 * 10) / 10;
  if (period === "month") return Math.round(value * 1.45 * 10) / 10;
  if (period === "quarter") return Math.round(value * 2.15 * 10) / 10;
  if (period === "half") return Math.round(value * 2.8 * 10) / 10;
  return value;
}

function averageValues(values: number[]) {
  const valid = values.filter((value) => Number.isFinite(value));
  if (!valid.length) return 0;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function averageMetricValues(points?: { value: number }[]) {
  return averageValues((points ?? []).map((point) => point.value));
}

function sumMetricValues(points?: { value: number }[]) {
  return (points ?? []).map((point) => point.value).filter(Number.isFinite).reduce((sum, value) => sum + value, 0);
}

function circleFontSize(name: string, radius: number) {
  if (name.length <= 4) return Math.min(15, Math.max(12, radius * 0.42));
  if (name.length <= 6) return Math.min(13, Math.max(10, radius * 0.34));
  return Math.min(11, Math.max(9, radius * 0.28));
}

function circleNameLines(name: string) {
  if (name.length <= 5) return [name];
  if (/^[A-Za-z0-9]+$/.test(name)) return [name];
  if (name.length <= 8) return [name.slice(0, 4), name.slice(4)];
  return [name.slice(0, 4), name.slice(4, 8), name.slice(8)];
}

function formatTradingValue(value: number) {
  if (!value) return "-";
  return fmtWon(Math.round(value));
}

function formatShortDate(date?: string) {
  if (!date) return "";
  const [, month, day] = date.split("-");
  return month && day ? `${month}/${day}` : date;
}

function metricPeriodText(issue: Issue, companies: Company[], period: Period) {
  const dates = companies
    .flatMap((company) => {
      const metric = company.metric?.[period];
      return [...(metric?.tradingValueIndex ?? []), ...(metric?.searchIndex ?? [])].map((point) => point.date);
    })
    .filter(Boolean)
    .sort();

  if (!dates.length) return period === "week" ? "7거래일" : "22거래일";
  const start = formatShortDate(dates[0]);
  const end = formatShortDate(dates[dates.length - 1]);
  return start === end ? `${end} 기준` : `${start}~${end}`;
}

function periodLabel(period: Period) {
  return PERIOD_OPTIONS.find((option) => option.value === period)?.label ?? "1주일";
}

function companyMetricForIssue(issue: Issue, companyId: string) {
  return getIssueMetricCache(issue.id)?.companies.find((metric) => metric.companyId === companyId);
}

function metricTradingValue(metric: ValueChainCompanyMetricCache | undefined, period: Period) {
  return sumMetricValues(metric?.[period]?.tradingValueIndex);
}

function metricSearchAverage(metric: ValueChainCompanyMetricCache | undefined, period: Period) {
  return averageMetricValues(metric?.[period]?.searchIndex);
}

function metricCurrentPrice(metric: ValueChainCompanyMetricCache | undefined, period: Period) {
  return metric?.[period]?.currentPrice ?? metric?.week?.currentPrice ?? metric?.month?.currentPrice ?? 0;
}

function uniqueIssuesByTitle(issues: Issue[]) {
  const seen = new Set<string>();
  return issues.filter((issue) => {
    const key = issue.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function buildCompanyReturnRows(period: Period) {
  const rows = new Map<
    string,
    {
      company: Company;
      issue: Issue;
      metric?: ValueChainCompanyMetricCache;
      returnPct: number;
      tradingValue: number;
      search: number;
      currentPrice: number;
      reason: string;
    }
  >();

  for (const issue of VALUE_CHAIN_ISSUES) {
    for (const companyId of domesticIssueCompanies(issue)) {
      const company = VALUE_CHAIN_COMPANIES[companyId];
      if (!company || company.region !== "domestic") continue;
      const metric = companyMetricForIssue(issue, companyId);
      const returnPct = metric?.[period]?.returnPct ?? periodReturn(company.returnPct, period);
      const tradingValue = metricTradingValue(metric, period);
      const search = metricSearchAverage(metric, period);
      const currentPrice = metricCurrentPrice(metric, period);
      const previous = rows.get(companyId);
      if (previous && previous.returnPct >= returnPct) continue;
      rows.set(companyId, {
        company,
        issue,
        metric,
        returnPct,
        tradingValue,
        search,
        currentPrice,
        reason: `${issue.title} 흐름과 연결됩니다. ${metric?.relation || company.detail}`,
      });
    }
  }

  return [...rows.values()].sort((a, b) => b.returnPct - a.returnPct);
}

function reviewText(status?: ValueChainDataStatus) {
  return status === "verified" ? null : "검토중";
}

function normalizeCategory(category: string): OrbitCategory {
  if (category === "산업") return "산업";
  if (category === "섹터" || category === "공정") return "섹터";
  if (category === "관련주" || category === "종목") return "관련주";
  return "이슈";
}

function categoryStyle(category: OrbitCategory) {
  if (category === "산업") {
    return {
      card: "border-blue-300/25 bg-blue-500/[0.16] hover:border-blue-200/55 hover:bg-blue-500/25",
      badge: "bg-blue-400/22 text-blue-100",
      text: "text-blue-100",
      gradient: "from-blue-300 to-indigo-400",
      center: "linear-gradient(150deg, #071637 0%, #1d4ed8 100%)",
      shadow: "rgba(59,130,246,0.46)",
    };
  }
  if (category === "섹터") {
    return {
      card: "border-cyan-300/22 bg-cyan-500/[0.13] hover:border-cyan-200/50 hover:bg-cyan-500/22",
      badge: "bg-cyan-400/20 text-cyan-100",
      text: "text-cyan-100",
      gradient: "from-cyan-300 to-blue-400",
      center: "linear-gradient(150deg, #08202a 0%, #0891b2 100%)",
      shadow: "rgba(34,211,238,0.36)",
    };
  }
  if (category === "관련주") {
    return {
      card: "border-emerald-300/22 bg-emerald-500/[0.13] hover:border-emerald-200/50 hover:bg-emerald-500/22",
      badge: "bg-emerald-400/20 text-emerald-100",
      text: "text-emerald-100",
      gradient: "from-emerald-300 to-teal-400",
      center: "linear-gradient(150deg, #08251c 0%, #059669 100%)",
      shadow: "rgba(16,185,129,0.36)",
    };
  }
  return {
    card: "border-violet-300/24 bg-violet-500/[0.14] hover:border-violet-200/55 hover:bg-violet-500/24",
    badge: "bg-violet-400/22 text-violet-100",
    text: "text-violet-100",
    gradient: "from-violet-300 to-fuchsia-400",
    center: "linear-gradient(150deg, #1d1239 0%, #7c3aed 100%)",
    shadow: "rgba(139,92,246,0.4)",
  };
}

function companyToOrbitItem(company: Company): OrbitItem {
  return {
    id: company.id,
    type: "company",
    name: company.name,
    role: company.role,
    detail: company.detail,
    score: company.score,
    category: "관련주",
    critical: company.critical,
  };
}

function issueToOrbitItem(issue: Issue, period: Period): OrbitItem {
  const domesticCount = domesticIssueCompanies(issue).length;
  return {
    id: issue.id,
    type: "issue",
    name: issue.title,
    role: `${issue.category} · 관련주 ${domesticCount}개`,
    detail: issue.desc,
    score: Math.round(issueAverageReturn(issue, period) ?? issue.composite),
    category: normalizeCategory(issue.category),
    critical: issue.category,
  };
}

function centerTitleLines(title: string) {
  const spaced = title.trim().split(/\s+/).filter(Boolean);
  if (spaced.length > 1) return spaced;
  if (title.endsWith("AI") && title.length > 4) return [title.slice(0, -2), "AI"];
  if (title.length <= 5) return [title];
  if (title.length <= 8) return [title.slice(0, 4), title.slice(4)];
  return [title.slice(0, 4), title.slice(4, 8), title.slice(8)];
}

function centerTitleSize(title: string) {
  const lines = centerTitleLines(title);
  const longest = Math.max(...lines.map((line) => line.length));
  if (lines.length === 1 && longest <= 5) return "text-[38px]";
  if (lines.length <= 2 && longest <= 5) return "text-[34px]";
  if (lines.length <= 2 && longest <= 7) return "text-[28px]";
  return "text-[24px]";
}

function ThemeScatter({ issue, companies, period }: { issue: Issue; companies: Company[]; period: Period }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const width = 760;
  const height = 420;
  const padding = { left: 72, right: 42, top: 46, bottom: 64 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const points = useMemo(
    () =>
      companies.map((company, index) => {
        const metric = company.metric?.[period];
        const fallbackSearch = generateSeries(issue, company, "search", period, index);
        const fallbackTrading = generateSeries(issue, company, "volume", period, index);
        const search = averageMetricValues(metric?.searchIndex) || averageValues(fallbackSearch);
        const tradingValue =
          sumMetricValues(metric?.tradingValueIndex) ||
          fallbackTrading.reduce((sum, value) => sum + value, 0) * (0.65 + company.marketCap / 4800000);
        const returnPct = metric?.returnPct ?? periodReturn(company.returnPct, period);
        return {
          company,
          search,
          tradingValue,
          returnPct,
          radius: 24 + Math.min(Math.max(returnPct, 0), 220) * 0.11,
          offsetX: ((index % 3) - 1) * 18,
          offsetY: ((Math.floor(index / 3) % 3) - 1) * 16,
          color: CHART_COLORS[index % CHART_COLORS.length],
        };
      }),
    [companies, issue, period],
  );
  const maxSearch = Math.max(...points.map((point) => point.search), 1);
  const minSearch = Math.min(...points.map((point) => point.search), 0);
  const maxTrading = Math.max(...points.map((point) => point.tradingValue), 1);
  const minTrading = Math.min(...points.map((point) => point.tradingValue), 0);
  const searchRange = maxSearch - minSearch || 1;
  const tradingRange = maxTrading - minTrading || 1;
  const leader = [...points].sort((a, b) => b.returnPct - a.returnPct)[0];
  const periodText = metricPeriodText(issue, companies, period);
  const toX = (value: number) => padding.left + ((value - minTrading) / tradingRange) * plotWidth;
  const toY = (value: number) => padding.top + plotHeight - ((value - minSearch) / searchRange) * plotHeight;
  const placedPoints = (() => {
    const minX = padding.left + 44;
    const maxX = padding.left + plotWidth - 44;
    const minY = padding.top + 44;
    const maxY = padding.top + plotHeight - 44;
    const placed = points.map((point) => {
      const rawX = toX(point.tradingValue) + point.offsetX;
      const rawY = toY(point.search) + point.offsetY;
      return {
        ...point,
        x: Math.max(minX, Math.min(maxX, rawX)),
        y: Math.max(minY, Math.min(maxY, rawY)),
      };
    });

    for (let step = 0; step < 90; step += 1) {
      for (let i = 0; i < placed.length; i += 1) {
        for (let j = i + 1; j < placed.length; j += 1) {
          const first = placed[i];
          const second = placed[j];
          const dx = second.x - first.x || 0.01;
          const dy = second.y - first.y || 0.01;
          const distance = Math.hypot(dx, dy);
          const minDistance = Math.min(first.radius + second.radius + 20, 112);
          if (distance < minDistance) {
            const push = (minDistance - distance) / 2;
            const nx = dx / distance;
            const ny = dy / distance;
            first.x = Math.max(minX, Math.min(maxX, first.x - nx * push));
            first.y = Math.max(minY, Math.min(maxY, first.y - ny * push));
            second.x = Math.max(minX, Math.min(maxX, second.x + nx * push));
            second.y = Math.max(minY, Math.min(maxY, second.y + ny * push));
          }
        }
      }
    }

    return placed;
  })();
  const hovered = placedPoints.find((point) => point.company.id === hoveredId);
  const tooltipPlacement = hovered
    ? {
        left: `${Math.min(Math.max((hovered.x / width) * 100, 22), 74)}%`,
        top: `${Math.min(Math.max((hovered.y / height) * 100, 22), 78)}%`,
        transform: hovered.y < height * 0.48 ? "translate(-50%, 18px)" : "translate(-50%, -112%)",
      }
    : undefined;

  return (
    <section className="rounded-[28px] border border-white/10 bg-white/[0.04] p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-black tracking-tight text-white">테마 종목 분포</h3>
          <p className="mt-1 text-xs font-bold text-white/35">
            {periodText} 기준 · x축 거래대금 합산 · y축 검색 관심도 평균 · 원 크기 기간 수익률
          </p>
        </div>
        <span className="rounded-full bg-blue-500/15 px-3 py-1 text-xs font-black text-blue-300">수익률 1위 {leader?.company.name}</span>
      </div>
      <div className="relative overflow-hidden rounded-[24px] bg-black/35">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[420px] w-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="scatter-grid" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="rgba(96,165,250,0.14)" />
              <stop offset="100%" stopColor="rgba(167,139,250,0.08)" />
            </linearGradient>
          </defs>
          <rect x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} rx="24" fill="url(#scatter-grid)" opacity="0.38" />
          {[0, 1, 2, 3, 4].map((line) => {
            const x = padding.left + (plotWidth / 4) * line;
            const y = padding.top + (plotHeight / 4) * line;
            return (
              <g key={line}>
                <line x1={x} x2={x} y1={padding.top} y2={padding.top + plotHeight} stroke="rgba(255,255,255,0.07)" />
                <line x1={padding.left} x2={padding.left + plotWidth} y1={y} y2={y} stroke="rgba(255,255,255,0.07)" />
              </g>
            );
          })}
          <line x1={padding.left} x2={padding.left + plotWidth} y1={padding.top + plotHeight} y2={padding.top + plotHeight} stroke="rgba(255,255,255,0.22)" />
          <line x1={padding.left} x2={padding.left} y1={padding.top} y2={padding.top + plotHeight} stroke="rgba(255,255,255,0.22)" />
          <text x={padding.left + plotWidth / 2} y={height - 18} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="13" fontWeight="800">
            거래대금 합산
          </text>
          <text x={padding.left + 4} y={padding.top - 30} fill="rgba(255,255,255,0.58)" fontSize="12" fontWeight="900">
            검색 관심도 평균
          </text>
          <text x={padding.left + 94} y={padding.top - 30} fill="rgba(255,255,255,0.28)" fontSize="10" fontWeight="800">
            높을수록 관심도 큼
          </text>
          <text x={padding.left + plotWidth} y={padding.top + plotHeight + 34} textAnchor="end" fill="rgba(255,255,255,0.28)" fontSize="11" fontWeight="800">
            오른쪽일수록 거래대금 합산 큼
          </text>
          {placedPoints.map((point) => {
            const x = point.x;
            const y = point.y;
            const active = hoveredId === point.company.id;
            const nameLines = circleNameLines(point.company.name);
            const fontSize = circleFontSize(point.company.name, point.radius);
            return (
              <g
                key={point.company.id}
                onMouseEnter={() => setHoveredId(point.company.id)}
                onMouseLeave={() => setHoveredId(null)}
                className="cursor-pointer"
              >
                <circle cx={x} cy={y} r={point.radius + 7} fill={point.color} opacity={active ? 0.24 : 0.1} />
                <circle cx={x} cy={y} r={point.radius} fill={point.color} opacity={active ? 0.95 : 0.74} stroke="rgba(255,255,255,0.45)" strokeWidth={active ? 2 : 1} />
                <text
                  x={x}
                  y={y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="white"
                  fontSize={fontSize}
                  fontWeight="900"
                  style={{ paintOrder: "stroke", stroke: "rgba(0,0,0,0.38)", strokeWidth: 3 }}
                >
                  {nameLines.map((line, lineIndex) => (
                    <tspan key={line} x={x} dy={lineIndex === 0 ? `${-(nameLines.length - 1) * fontSize * 0.34}px` : `${fontSize * 1.05}px`}>
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}
        </svg>
        {hovered ? (
          <div
            className="pointer-events-none absolute z-20 w-[240px] rounded-2xl border border-white/10 bg-[#11131a]/95 p-4 text-white shadow-2xl backdrop-blur-xl"
            style={tooltipPlacement}
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-black text-blue-300">{hovered.company.name}</p>
              <span className="shrink-0 rounded-full bg-white/8 px-2 py-0.5 text-[10px] font-black text-white/55">{periodText}</span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] font-bold text-white/45">
              <span>기업명</span>
              <span className="text-right text-white">{hovered.company.name}</span>
              <span>거래대금 합산</span>
              <span className="text-right text-white">{formatTradingValue(hovered.tradingValue)}</span>
              <span>검색 관심도 평균</span>
              <span className="text-right text-white">{Math.round(hovered.search).toLocaleString()}</span>
              <span>기간 수익률</span>
              <span className="text-right text-white">{fmtPct(hovered.returnPct)}</span>
            </div>
            <p className="mt-3 text-[10px] font-bold leading-4 text-white/35">
              검색 관심도는 네이버 검색어트렌드 상대지수라 실제 검색 건수가 아닙니다. 거래대금은 KRX 일별 거래대금 합산, 수익률은 선택 기간 첫 종가 대비 마지막 종가 기준입니다.
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function OrbitStage({
  center,
  items,
  onOpenPanel,
  onOpenItem,
}: {
  center: OrbitCenter;
  items: OrbitItem[];
  onOpenPanel: () => void;
  onOpenItem: (item: OrbitItem) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    let raf = 0;
    let start = 0;
    const period = 46000;

    const tick = (time: number) => {
      if (!start) start = time;
      const rect = stage.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const count = Math.max(Math.min(items.length, 12), 1);
      const sparseBoost = count <= 6 ? 1.16 : 1;
      const rx = Math.min(rect.width * 0.36 * sparseBoost, 460);
      const ry = Math.min(rect.height * 0.28 * sparseBoost, 285);
      const global = ((time - start) / period) * TAU;
      const track = stage.querySelector<SVGEllipseElement>("[data-track]");
      if (track) {
        track.setAttribute("cx", String(cx));
        track.setAttribute("cy", String(cy));
        track.setAttribute("rx", String(rx));
        track.setAttribute("ry", String(ry));
      }
      stage.querySelectorAll<HTMLElement>("[data-orbit-card]").forEach((card) => {
        const base = Number(card.dataset.angle ?? 0);
        const width = Number(card.dataset.width ?? 168);
        const height = Number(card.dataset.height ?? 98);
        const angle = base + global;
        const depth = (Math.sin(angle) + 1) / 2;
        const scale = 0.98 + depth * 0.06;
        const x = cx + Math.cos(angle) * rx - width / 2;
        const y = cy + Math.sin(angle) * ry - height / 2;
        const glowAlpha = Math.max(0, depth - 0.65) / 0.35;
        card.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${scale})`;
        card.style.opacity = "0.96";
        card.style.zIndex = String(Math.round(10 + depth * 30));
        card.style.filter = "none";
        card.style.setProperty("--orbit-glow", String(glowAlpha));
      });

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [items.length, center.title]);

  return (
    <div ref={stageRef} className="absolute inset-0 overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 50% 44% at 50% 50%, rgba(37,99,235,0.22), transparent 62%), radial-gradient(ellipse 82% 62% at 50% 50%, transparent 0%, rgba(0,0,0,0.52) 72%, rgba(0,0,0,0.9) 100%)",
        }}
      />
      <svg className="pointer-events-none absolute inset-0 h-full w-full">
        <ellipse data-track cx="50%" cy="50%" rx="100" ry="100" fill="none" stroke="rgba(255,255,255,0.045)" strokeWidth="1" strokeDasharray="4 6" />
      </svg>
      {items.slice(0, 12).map((item, index) => {
        const baseAngle = (TAU / Math.max(items.slice(0, 12).length, 1)) * index - Math.PI / 2;
        const style = categoryStyle(item.category);
        return (
          <button
            key={`${item.type}-${item.id}`}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenItem(item);
            }}
            data-orbit-card
            data-angle={baseAngle}
            data-width="164"
            data-height="134"
            className="absolute left-0 top-0 h-[134px] w-[164px] cursor-pointer select-none rounded-[34px] bg-transparent p-0 will-change-transform hover:!z-[70]"
            title={item.detail}
          >
            <div
              className={`flex h-full flex-col rounded-[34px] border px-4 py-3.5 text-white backdrop-blur-lg transition-colors ${style.card}`}
              style={{
                boxShadow:
                  `0 8px 32px rgba(0,0,0,0.45), 0 0 calc(var(--orbit-glow, 0) * 30px) ${style.shadow}`,
              }}
            >
              <div className="mb-1.5 flex items-start justify-between gap-2">
                <span className="min-w-0 break-keep text-[13px] font-black leading-tight tracking-tight">{item.name}</span>
              </div>
              <p className="mb-3 truncate text-[11px] font-bold text-blue-200/65">{item.role}</p>
              <div className="mt-auto h-[3px] overflow-hidden rounded-full bg-white/10">
                <div className={`h-full rounded-full bg-gradient-to-r ${style.gradient}`} style={{ width: `${Math.min(Math.max(item.score, 5), 100)}%` }} />
              </div>
              <span className={`mt-2 inline-flex w-fit rounded-full px-2 py-0.5 text-[9px] font-black ${style.badge}`}>{item.category}</span>
            </div>
          </button>
        );
      })}
      {(() => {
        const style = categoryStyle(center.category);
        return (
      <button
        type="button"
        onClick={onOpenPanel}
        className="absolute left-1/2 top-1/2 z-40 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center text-center text-white transition-transform duration-300 hover:scale-[1.04]"
        style={{
          width: 260,
          height: 260,
          borderRadius: 54,
          background: `radial-gradient(circle at 35% 25%, rgba(255,255,255,0.18), transparent 28%), ${style.center}`,
          border: "1px solid rgba(255,255,255,0.16)",
          boxShadow: `0 0 84px ${style.shadow}, 0 36px 80px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.12)`,
        }}
      >
        <span className="pointer-events-none absolute inset-0 rounded-[54px] border border-white/14 [animation:vc-pulse_2.8s_ease-out_infinite]" />
        <span className="pointer-events-none absolute -inset-3.5 rounded-[60px] border border-white/10 [animation:vc-pulse_3.4s_ease-out_infinite_0.6s]" />
        <span className={`mb-4 rounded-full px-3 py-1 text-[10px] font-black ${style.badge}`}>{center.category}</span>
        <span className={`max-w-[220px] truncate break-keep px-3 text-center ${centerTitleSize(center.title)} font-black leading-none tracking-tight`}>
          {center.title}
        </span>
        <span className="mt-4 rounded-full bg-white px-5 py-2 text-[12px] font-black text-blue-700 shadow-lg">비교 보기</span>
      </button>
        );
      })()}
    </div>
  );
}

function StockReturnTable({
  period,
  setPeriod,
  onSelectIssue,
  onSelectCompany,
}: {
  period: Period;
  setPeriod: (period: Period) => void;
  onSelectIssue: (issueId: string) => void;
  onSelectCompany: (companyId: string) => void;
}) {
  const rows = useMemo(() => buildCompanyReturnRows(period).slice(0, 40), [period]);
  const periodText = rows.length ? metricPeriodText(rows[0].issue, rows.map((row) => row.company), period) : periodLabel(period);

  return (
    <div className="absolute inset-0 overflow-auto px-8 pb-8 pt-24 text-white">
      <section className="mx-auto max-w-[1280px] rounded-[30px] border border-white/10 bg-[#0b0d13]/88 p-6 shadow-[0_30px_90px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-1 text-[10px] font-black uppercase tracking-[0.22em] text-blue-400">종목 상승률</p>
            <h2 className="text-3xl font-black tracking-tight">테마 관련주 상승률</h2>
            <p className="mt-2 text-xs font-bold text-white/38">
              {periodText} 기준 · 거래대금은 기간 합산 · 검색 관심도는 네이버 상대지수 평균 · 수익률은 기간 첫 종가 대비 마지막 종가
            </p>
          </div>
          <div className="inline-flex rounded-full border border-white/10 bg-white/10 p-1">
            {PERIOD_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setPeriod(value)}
                className={`whitespace-nowrap rounded-full px-3.5 py-2 text-xs font-black transition ${
                  period === value ? "bg-blue-600 text-white shadow-md" : "text-white/45 hover:text-white/70"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-hidden rounded-2xl border border-white/10">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-white/[0.05]">
              <tr className="border-b border-white/10 text-left">
                {["순위", "종목", "현재가", `${periodLabel(period)} 등락률`, "시가총액", "거래대금", "테마", "상승 이유"].map((head, index) => (
                  <th
                    key={head}
                    className={`px-4 py-3 text-[11px] font-black text-white/42 ${
                      index >= 2 && index <= 5 ? "text-right" : index === 7 ? "text-left" : ""
                    }`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`return-${row.company.id}`} className="border-t border-white/6 transition hover:bg-white/[0.04]">
                  <td className="w-14 px-4 py-3 text-center font-black text-white/38">{index + 1}</td>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => onSelectCompany(row.company.id)} className="font-black text-blue-300 hover:text-blue-100">
                      {row.company.name}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-black tabular-nums text-white">
                    {row.currentPrice ? `${row.currentPrice.toLocaleString()}원` : "-"}
                  </td>
                  <td className={`whitespace-nowrap px-4 py-3 text-right font-black tabular-nums ${row.returnPct >= 0 ? "text-rose-300" : "text-blue-300"}`}>
                    {fmtPct(row.returnPct)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/58">{fmtWon(row.company.marketCap)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/58">{formatTradingValue(row.tradingValue)}</td>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => onSelectIssue(row.issue.id)} className="rounded-full bg-blue-500/14 px-3 py-1 text-xs font-black text-blue-200 hover:bg-blue-500/24">
                      {row.issue.title}
                    </button>
                  </td>
                  <td className="max-w-[420px] px-4 py-3 text-xs font-semibold leading-5 text-white/45">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ComparePanel({
  issue,
  companies,
  period,
  setPeriod,
  onClose,
  panelWidth,
  onResizeStart,
  onSelectIssue,
  focusCompany,
  relatedIssues,
}: {
  issue: Issue;
  companies: Company[];
  period: Period;
  setPeriod: (period: Period) => void;
  onClose: () => void;
  panelWidth: number;
  onResizeStart: (event: PointerEvent<HTMLDivElement>) => void;
  onSelectIssue: (issueId: string) => void;
  focusCompany?: Company | null;
  relatedIssues?: Issue[];
}) {
  const rows = useMemo(
    () => companies.slice(0, 10).map((company, index) => ({ company, score: Math.max(40, company.score - index) })).sort((a, b) => b.score - a.score),
    [companies],
  );

  return (
    <aside
      className="absolute bottom-0 right-0 top-0 z-[80] overflow-auto border-l border-white/10 bg-[#07080b]/95 shadow-[-32px_0_80px_rgba(0,0,0,0.55)] backdrop-blur-2xl transition-[width] duration-500"
      style={{ width: panelWidth }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="상세 패널 폭 조절"
        onPointerDown={onResizeStart}
        className="absolute bottom-0 left-0 top-0 z-[95] w-2 cursor-col-resize border-l border-blue-400/25 bg-blue-400/0 transition hover:bg-blue-400/10"
      />
      <div className="sticky top-0 z-[90] border-b border-white/10 bg-[#07080b]/95 px-7 py-4 backdrop-blur-2xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute left-4 top-4 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/10 text-lg font-black text-white/55 transition hover:bg-white/15 hover:text-white"
          aria-label="상세 패널 닫기"
        >
          ×
        </button>
        <div className="flex items-center justify-between gap-4 pl-12">
        <div>
          <p className="mb-0.5 text-[10px] font-black uppercase tracking-[0.22em] text-blue-400">{focusCompany ? "종목 연결망" : "관련주 비교"}</p>
          <h2 className="text-3xl font-black tracking-tight text-white">{focusCompany ? `${focusCompany.name} 관련 테마` : issue.title}</h2>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="inline-flex rounded-full border border-white/10 bg-white/10 p-1">
            {PERIOD_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setPeriod(value)}
                className={`whitespace-nowrap rounded-full px-4 py-2 text-xs font-black transition ${period === value ? "bg-blue-600 text-white shadow-md" : "text-white/45 hover:text-white/65"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="rounded-full border border-white/12 bg-white/10 px-4 py-2 text-sm font-black text-white">
            평균 {fmtPct(issueAverageReturn(issue, period) ?? 0)}
          </span>
        </div>
        </div>
      </div>
      <div className="px-7 py-6">
        <p className="mb-5 text-sm font-semibold leading-7 text-white/45">
          {focusCompany ? `${focusCompany.name}이 연결된 테마와 섹터를 모아 봅니다. 종목을 기준으로 시장 이슈를 거슬러 올라가는 화면입니다.` : issue.desc}
        </p>
        {focusCompany ? (
          <div className="mb-6 overflow-hidden rounded-2xl border border-blue-400/20 bg-blue-500/[0.06]">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-white/[0.03]">
                <tr className="border-b border-white/10">
                  {["테마·섹터", "분류", "평균 수익률", "연결 이유"].map((head, index) => (
                    <th key={head} className={`px-4 py-3 text-[10px] font-black uppercase tracking-wider text-white/35 ${index === 3 ? "text-left" : index === 2 ? "text-right" : "text-left"}`}>
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(relatedIssues || []).map((relatedIssue) => (
                  <tr key={relatedIssue.id} className="border-t border-white/5 align-top hover:bg-white/[0.04]">
                    <td className="whitespace-nowrap px-4 py-3">
                      <button type="button" onClick={() => onSelectIssue(relatedIssue.id)} className="font-black text-blue-300 hover:text-blue-100">
                        {relatedIssue.title}
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs font-bold text-white/45">{relatedIssue.category}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-black tabular-nums text-rose-200">{fmtPct(issueAverageReturn(relatedIssue, period) ?? 0)}</td>
                    <td className="px-4 py-3 text-xs font-semibold leading-5 text-white/45">{relatedIssue.desc}</td>
                  </tr>
                ))}
                {!(relatedIssues || []).length ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-sm font-bold text-white/35">
                      연결된 테마가 없습니다.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}
        {focusCompany ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-8 text-center">
            <p className="text-lg font-black text-white">관련주 없음</p>
            <p className="mt-2 text-sm font-semibold text-white/40">종목 중심 화면에서는 연결 테마를 먼저 보여주고, 테마를 누르면 그 테마의 관련주 분포로 이동합니다.</p>
          </div>
        ) : (
          <ThemeScatter issue={issue} companies={companies} period={period} />
        )}
        {!focusCompany ? (
          <>
        <div className="mt-6 overflow-hidden rounded-2xl border border-white/10">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-white/[0.03]">
              <tr className="border-b border-white/10">
                {["종목", "연관성"].map((head, index) => (
                  <th key={head} className={`px-4 py-3 text-[10px] font-black uppercase tracking-wider text-white/30 ${index === 0 ? "w-[150px] text-left" : "text-left"}`}>
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ company }) => (
                <tr key={`rel-${company.id}`} className="border-t border-white/5 align-top hover:bg-white/[0.03]">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="whitespace-nowrap font-black text-blue-300">{company.name}</span>
                      {company.critical ? <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-[9px] font-black text-amber-300">{company.critical}</span> : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs font-semibold leading-5 text-white/45">{company.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-6 overflow-hidden rounded-2xl border border-white/10">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-white/[0.03]">
              <tr className="border-b border-white/10">
              {["종목", "관련도", "시가총액", "연매출", "연영업익", "분기매출", "분기영업익", "수익률"].map((head, index) => (
                  <th key={head} className={`px-4 py-3 text-[10px] font-black uppercase tracking-wider text-white/30 ${index === 0 ? "text-left" : "text-right"}`}>
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ company, score }, index) => {
                const shownReturn = periodReturn(company.returnPct, period);
                const needsReview = reviewText(company.financialStatus);
                const financialValue = (value: number) =>
                  value ? fmtWon(value) : <span className="text-amber-300/70">{needsReview ?? "확인중"}</span>;
                return (
                  <tr key={`fin-${company.id}`} className="border-t border-white/5 transition-colors hover:bg-white/[0.03]" style={{ backgroundColor: index === 0 ? "rgba(37,99,235,0.1)" : undefined }}>
                    <td className="px-4 py-3 font-black text-blue-300">{company.name}</td>
                    <td className="px-4 py-3 text-right font-black tabular-nums text-white">{score}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/50">{financialValue(company.marketCap)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/50">{financialValue(company.sales)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/50">{financialValue(company.op)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/50">{financialValue(company.quarterSales)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums text-white/50">{financialValue(company.quarterOp)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-black tabular-nums" style={{ color: shownReturn > 0 ? "#4ade80" : "#f87171" }}>
                      {fmtPct(shownReturn)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}

export function ValueChainDemo() {
  const [menuOpen, setMenuOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("map");
  const [detailPanelWidth, setDetailPanelWidth] = useState(DEFAULT_DETAIL_PANEL_WIDTH);
  const [focusCompanyId, setFocusCompanyId] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("week");
  const [query, setQuery] = useState("");
  const [searchCategory, setSearchCategory] = useState<"전체" | OrbitCategory>("전체");
  const [selectedId, setSelectedId] = useState(VALUE_CHAIN_ISSUES[0].id);
  const [navHistory, setNavHistory] = useState<NavState[]>([]);
  const selectedIssue = VALUE_CHAIN_NAV_ISSUES.find((issue) => issue.id === selectedId) ?? VALUE_CHAIN_ISSUES[0];
  const pushNavigation = (nextState: NavState) => {
    setNavHistory((history) => [...history, { selectedId, focusCompanyId }].slice(-20));
    setSelectedId(nextState.selectedId);
    setFocusCompanyId(nextState.focusCompanyId);
    setPanelOpen(false);
    setSearchOpen(false);
  };
  const goBack = () => {
    setNavHistory((history) => {
      const previous = history.at(-1);
      if (!previous) return history;
      setSelectedId(previous.selectedId);
      setFocusCompanyId(previous.focusCompanyId);
      setPanelOpen(false);
      setSearchOpen(false);
      return history.slice(0, -1);
    });
  };
  const companies = useMemo(() => {
    const metricMap = new Map((getIssueMetricCache(selectedIssue.id)?.companies || []).map((metric) => [metric.companyId, metric]));
    return domesticIssueCompanies(selectedIssue)
      .map((id) => {
        const company = VALUE_CHAIN_COMPANIES[id];
        const metric = metricMap.get(id);
        if (!company) return null;
        const enrichedCompany: Company = {
          ...company,
          metric: metric ?? undefined,
          score: metric?.score ?? company.score,
          returnPct: metric?.[period]?.returnPct ?? company.returnPct,
        };
        return enrichedCompany;
      })
      .filter((company): company is Company => Boolean(company));
  }, [selectedIssue, period]);
  const startPanelResize = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = detailPanelWidth;
    const maxWidth = Math.min(MAX_DETAIL_PANEL_WIDTH, Math.floor(window.innerWidth * 0.78));

    const handleMove = (moveEvent: globalThis.PointerEvent) => {
      const nextWidth = startWidth + (startX - moveEvent.clientX);
      setDetailPanelWidth(Math.min(maxWidth, Math.max(MIN_DETAIL_PANEL_WIDTH, nextWidth)));
    };

    const handleUp = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp, { once: true });
  };
  const focusCompany = focusCompanyId ? VALUE_CHAIN_COMPANIES[focusCompanyId] : null;
  const focusCompanyIssues = useMemo(
    () =>
      focusCompanyId
        ? uniqueIssuesByTitle(VALUE_CHAIN_NAV_ISSUES.filter((issue) => issue.companyIds.includes(focusCompanyId))).sort((a, b) => {
            const aReal = a.id.startsWith("topic-") ? 0 : 1;
            const bReal = b.id.startsWith("topic-") ? 0 : 1;
            return bReal - aReal || (issueAverageReturn(b, period) ?? -999) - (issueAverageReturn(a, period) ?? -999);
          })
        : [],
    [focusCompanyId, period],
  );
  const center: OrbitCenter = focusCompany
    ? {
        title: focusCompany.name,
        category: "관련주",
        subtitle: "",
      }
    : {
        title: selectedIssue.title,
        category: normalizeCategory(selectedIssue.category),
        subtitle: "",
      };
  const orbitItems = useMemo(
    () => (focusCompany ? focusCompanyIssues.map((issue) => issueToOrbitItem(issue, period)) : companies.map(companyToOrbitItem)),
    [companies, focusCompany, focusCompanyIssues, period],
  );
  const rankedIssues = useMemo(
    () =>
      [...VALUE_CHAIN_ISSUES].sort((a, b) => {
        const left = issueAverageReturn(a, period);
        const right = issueAverageReturn(b, period);
        return (right ?? -999) - (left ?? -999);
      }),
    [period],
  );
  const visibleIssues = useMemo(() => {
    return rankedIssues.slice(0, 10);
  }, [rankedIssues]);
  const searchableIssues = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const issueResults: SearchResult[] =
      searchCategory === "관련주"
        ? []
        : VALUE_CHAIN_NAV_ISSUES.map((issue) => ({
            id: issue.id,
            type: "issue" as const,
            title: issue.title,
            category: normalizeCategory(issue.category),
            desc: issue.desc,
            countText: `국내 관련주 ${domesticIssueCompanies(issue).length}개`,
          })).filter((item) => searchCategory === "전체" || item.category === searchCategory);
    const companyResults: SearchResult[] =
      searchCategory === "전체" || searchCategory === "관련주"
        ? Object.values(VALUE_CHAIN_COMPANIES)
            .filter((company) => company.region === "domestic")
            .map((company) => ({
              id: company.id,
              type: "company" as const,
              title: company.name,
              category: "관련주" as const,
              desc: company.role,
              countText: company.role,
            }))
        : [];
    return [...issueResults, ...companyResults]
      .filter((item) => (keyword ? `${item.title} ${item.category} ${item.desc}`.toLowerCase().includes(keyword) : true))
      .sort((a, b) => a.title.localeCompare(b.title, "ko"));
  }, [query, searchCategory]);
  const categoryFilters: Array<"전체" | OrbitCategory> = ["전체", "산업", "섹터", "관련주", "이슈"];

  return (
    <div className="relative h-[calc(100vh-120px)] min-h-[860px] overflow-hidden rounded-[32px] border border-white/10 bg-[#07080b] shadow-[0_40px_120px_rgba(0,0,0,0.8)]">
      <style>{`
        @keyframes vc-pulse {
          0% { opacity: 1; transform: scale(1); }
          100% { opacity: 0; transform: scale(1.45); }
        }
      `}</style>
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.024)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.024)_1px,transparent_1px)] bg-[size:64px_64px]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_48%,rgba(37,99,235,0.16),transparent_38%),radial-gradient(circle_at_14%_22%,rgba(139,92,246,0.1),transparent_28%)]" />
      <header className="absolute left-8 right-8 top-6 z-[75] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={goBack}
            disabled={!navHistory.length}
            className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/10 text-lg font-black text-white backdrop-blur-lg transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-35"
            aria-label="이전 탐색으로 돌아가기"
          >
            &lt;
          </button>
          <button
            type="button"
            onClick={() => {
              setViewMode("map");
              setPeriod("week");
              setMenuOpen((value) => !value);
            }}
            className="rounded-full border border-white/10 bg-white/10 px-5 py-2.5 text-sm font-black text-white backdrop-blur-lg transition hover:bg-white/15"
          >
            {menuOpen ? "테마 닫기" : "테마 선택"}
          </button>
          <button
            type="button"
            onClick={() => {
              setViewMode((value) => (value === "returns" ? "map" : "returns"));
              setPanelOpen(false);
              setMenuOpen(false);
              setSearchOpen(false);
            }}
            className={`rounded-full border px-5 py-2.5 text-sm font-black backdrop-blur-lg transition ${
              viewMode === "returns" ? "border-blue-400/35 bg-blue-600 text-white" : "border-white/10 bg-white/10 text-white hover:bg-white/15"
            }`}
          >
            종목 상승률
          </button>
        </div>
        <div className={`text-right transition-opacity duration-200 ${panelOpen ? "pointer-events-none opacity-0" : "opacity-100"}`}>
          <p className="text-[13px] font-black lowercase tracking-[0.18em] text-white/[0.28]">vericap</p>
        </div>
      </header>
      {menuOpen ? (
        <aside className="absolute bottom-8 left-8 top-20 z-[70] flex w-[280px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.07] p-5 text-white shadow-[0_30px_80px_rgba(0,0,0,0.4)] backdrop-blur-2xl">
          <div className="mb-4">
            <p className="mb-1 text-[10px] font-black uppercase tracking-[0.22em] text-blue-400">시장 이슈</p>
            <div className="flex items-end justify-between gap-3">
              <h2 className="text-2xl font-black leading-tight">테마 순위</h2>
              <div className="inline-flex rounded-full border border-white/10 bg-black/20 p-1">
                {PERIOD_OPTIONS.slice(1, 3).map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setPeriod(value)}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-black transition ${
                      period === value ? "bg-blue-600 text-white" : "text-white/40 hover:text-white/70"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <p className="mt-2 text-[10px] font-bold text-white/35">관련주 평균 수익률 기준</p>
          </div>
          <button
            type="button"
            onClick={() => setSearchOpen((value) => !value)}
            className={`mb-3 h-10 w-full rounded-2xl border px-4 text-left text-sm font-black transition ${
              searchOpen ? "border-blue-400/60 bg-blue-600/20 text-blue-100" : "border-white/10 bg-black/25 text-white/55 hover:text-white"
            }`}
          >
            검색
          </button>
          <div className="flex-1 space-y-1.5 overflow-auto pr-0.5">
            {visibleIssues.map((issue, index) => {
              const active = issue.id === selectedId;
              return (
                <button
                  key={issue.id}
                  type="button"
                  onClick={() => {
                    pushNavigation({ selectedId: issue.id, focusCompanyId: null });
                  }}
                  className={`w-full rounded-[18px] border px-4 py-3 text-left transition ${
                    active ? "border-blue-400/35 bg-blue-600/30 shadow-[0_12px_36px_rgba(37,99,235,0.18)]" : "border-white/10 bg-white/[0.04] hover:bg-white/[0.09]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-[13px] font-black">{issue.title}</span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black tabular-nums ${
                        (issueAverageReturn(issue, period) ?? 0) >= 0 ? "bg-rose-500/18 text-rose-200" : "bg-blue-500/18 text-blue-200"
                      }`}
                    >
                      {fmtPct(issueAverageReturn(issue, period) ?? 0)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[10px] font-bold text-white/35">
                    {index + 1}위 · {issue.category} · 국내 산출 {issueReturnCount(issue, period)}개
                  </p>
                </button>
              );
            })}
          </div>
        </aside>
      ) : null}
      {menuOpen && searchOpen ? (
        <aside className="absolute bottom-8 left-[328px] top-20 z-[110] flex w-[320px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[#0b0d13]/95 p-5 text-white shadow-[0_30px_80px_rgba(0,0,0,0.45)] backdrop-blur-2xl">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="mb-1 text-[10px] font-black uppercase tracking-[0.22em] text-blue-400">전체 목록</p>
              <h2 className="text-xl font-black">ㄱㄴㄷ 검색</h2>
            </div>
            <button
              type="button"
              onClick={() => setSearchOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/10 text-sm font-black text-white/50 hover:text-white"
              aria-label="검색 패널 닫기"
            >
              ×
            </button>
          </div>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="테마·섹터 검색"
            className="mb-3 h-10 w-full rounded-2xl border border-white/10 bg-black/25 px-4 text-sm font-bold text-white outline-none placeholder:text-white/30 transition focus:border-blue-400"
          />
          <div className="mb-3 flex flex-wrap gap-1.5">
            {categoryFilters.map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => setSearchCategory(category)}
                className={`rounded-full px-3 py-1.5 text-[10px] font-black transition ${
                  searchCategory === category ? "bg-blue-600 text-white" : "bg-white/8 text-white/45 hover:bg-white/12 hover:text-white"
                }`}
              >
                {category}
              </button>
            ))}
          </div>
          <div className="flex-1 space-y-1.5 overflow-auto pr-0.5">
            {searchableIssues.map((item) => {
              const style = categoryStyle(item.category);
              return (
                <button
                  key={`search-${item.type}-${item.id}`}
                  type="button"
                  onClick={() => {
                    if (item.type === "issue") {
                      pushNavigation({ selectedId: item.id, focusCompanyId: null });
                      return;
                    }
                    pushNavigation({ selectedId, focusCompanyId: item.id });
                  }}
                  className="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left transition hover:bg-white/[0.08]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-black text-white">{item.title}</span>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-black ${style.badge}`}>{item.category}</span>
                  </div>
                  <p className="mt-1 truncate text-[10px] font-bold text-white/35">{item.countText}</p>
                </button>
              );
            })}
            {!searchableIssues.length ? <p className="py-10 text-center text-sm font-bold text-white/35">검색 결과가 없습니다.</p> : null}
          </div>
        </aside>
      ) : null}
      <main
        className="absolute inset-0 z-10 transition-all duration-500"
        style={{
          left: 0,
          right: panelOpen ? detailPanelWidth : 0,
        }}
      >
        {viewMode === "returns" ? (
          <StockReturnTable
            period={period}
            setPeriod={setPeriod}
            onSelectIssue={(issueId) => {
              setViewMode("map");
              pushNavigation({ selectedId: issueId, focusCompanyId: null });
            }}
            onSelectCompany={(companyId) => {
              setViewMode("map");
              pushNavigation({ selectedId, focusCompanyId: companyId });
            }}
          />
        ) : (
          <OrbitStage
            center={center}
            items={orbitItems}
            onOpenPanel={() => {
              setPanelOpen(true);
            }}
            onOpenItem={(item) => {
              if (item.type === "company") {
                pushNavigation({ selectedId, focusCompanyId: item.id });
                return;
              }
              pushNavigation({ selectedId: item.id, focusCompanyId: null });
            }}
          />
        )}
      </main>
      {panelOpen ? (
        <ComparePanel
          issue={selectedIssue}
          companies={companies}
          period={period}
          setPeriod={setPeriod}
          onClose={() => setPanelOpen(false)}
          panelWidth={detailPanelWidth}
          onResizeStart={startPanelResize}
          onSelectIssue={(issueId) => pushNavigation({ selectedId: issueId, focusCompanyId: null })}
          focusCompany={focusCompany}
          relatedIssues={focusCompanyIssues}
        />
      ) : null}
    </div>
  );
}
