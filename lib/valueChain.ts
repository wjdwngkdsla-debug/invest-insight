import companiesData from "@/data/value-chain/companies.json";
import financialsData from "@/data/value-chain/financials.json";
import issuesData from "@/data/value-chain/issues.json";
import marketMetricsData from "@/data/value-chain/market-metrics.json";
import relationsData from "@/data/value-chain/relations.json";
import sourcesData from "@/data/value-chain/sources.json";
import topicsData from "@/data/value-chain/topics.json";

export type ChainLayer = "product" | "process" | "equipment" | "material";
export type CompanyRegion = "domestic" | "overseas";
export type CompanyListing = "listed" | "private";
export type ValueChainMode = "valueChain" | "marketIssue" | "theme";
export type ValueChainTopicKind = "hub" | "market" | "process" | "theme" | "company";
export type ValueChainDataStatus = "verified" | "draft" | "needsReview";

export interface ValueChainSource {
  id: string;
  label: string;
  url?: string;
  checkedAt: string;
  note: string;
}

export interface ValueChainCompany {
  id: string;
  name: string;
  layer: ChainLayer;
  role: string;
  roleDetail?: string;
  processIds: string[];
  region: CompanyRegion;
  listing: CompanyListing;
  critical?: "핵심" | "독점";
  ticker?: string;
  dataStatus?: ValueChainDataStatus;
  sourceIds?: string[];
  financialAsOf?: string;
  financialSourceIds?: string[];
  financialStatus?: ValueChainDataStatus;
  verificationNote?: string;
  marketCap?: number;
  sales: [number, number, number];
  operatingProfit: [number, number, number];
  opMargin: number;
  per?: number;
  oneYearReturn?: number;
}

export interface ValueChainNode {
  id: string;
  title: string;
  subtitle: string;
  layer: ChainLayer;
  parentId?: string;
  x: number;
  y: number;
  companyIds: string[];
  keywords: string[];
  description?: string;
  dataStatus?: ValueChainDataStatus;
  sourceIds?: string[];
}

export interface ValueChainTopic extends ValueChainNode {
  kind: ValueChainTopicKind;
  mode: ValueChainMode;
  note: string;
  layerType?: "industry" | "sector" | ValueChainTopicKind;
}

export interface ValueChainLink {
  source: string;
  target: string;
  relation?: string;
  dataStatus?: ValueChainDataStatus;
}

export interface ValueChainTrendPoint {
  date: string;
  search: number;
  price: number;
  volume: number;
}

export interface ValueChainIssueScore {
  id: string;
  topicId: string;
  title: string;
  category: "산업" | "섹터" | "테마" | "수급";
  description: string;
  companyIds: string[];
  relatedTopicIds: string[];
  netBuyRank?: number;
  returnScore: number;
  searchScore: number;
  volumeScore: number;
  avgReturnPct: number;
  searchChangePct: number;
  volumeChangePct: number;
  trend: ValueChainTrendPoint[];
  composite?: number;
}

export interface ValueChainFinancialCache {
  companyId: string;
  asOf: string;
  status: ValueChainDataStatus;
  sourceIds: string[];
  marketCap: number | null;
  annual: {
    sales: [number, number, number];
    operatingProfit: [number, number, number];
    opMargin: number;
    per: number | null;
  };
  recentQuarter: {
    sales: number;
    operatingProfit: number;
  };
}

export interface ValueChainMetricPoint {
  date: string;
  value: number;
}

export interface ValueChainCompanyMetricCache {
  companyId: string;
  issueId: string;
  role: string;
  relation: string;
  score: number;
  day?: {
    searchIndex: ValueChainMetricPoint[];
    tradingValueIndex: ValueChainMetricPoint[];
    returnPct: number;
    currentPrice?: number;
  };
  week?: {
    searchIndex: ValueChainMetricPoint[];
    tradingValueIndex: ValueChainMetricPoint[];
    returnPct: number;
    currentPrice?: number;
  };
  month?: {
    searchIndex: ValueChainMetricPoint[];
    tradingValueIndex: ValueChainMetricPoint[];
    returnPct: number;
    currentPrice?: number;
  };
  quarter?: {
    searchIndex: ValueChainMetricPoint[];
    tradingValueIndex: ValueChainMetricPoint[];
    returnPct: number;
    currentPrice?: number;
  };
  half?: {
    searchIndex: ValueChainMetricPoint[];
    tradingValueIndex: ValueChainMetricPoint[];
    returnPct: number;
    currentPrice?: number;
  };
}

export interface ValueChainIssueMetricCache {
  issueId: string;
  topicId: string;
  score: {
    composite: number;
    returnScore: number;
    searchScore: number;
    tradingValueScore: number;
  };
  summary: {
    avgReturnPct: number;
    searchChangePct: number;
    tradingValueChangePct: number;
  };
  companies: ValueChainCompanyMetricCache[];
}

export interface ValueChainMarketMetricsCache {
  generatedAt: string;
  status: "demo-cache" | "live-cache";
  note: string;
  issues: ValueChainIssueMetricCache[];
}

export const layerLabels: Record<ChainLayer, string> = {
  product: "제품/수요처",
  process: "공정",
  equipment: "소재·장비",
  material: "소재·부품",
};

type CompanyProfile = Omit<
  ValueChainCompany,
  "financialAsOf" | "financialSourceIds" | "financialStatus" | "marketCap" | "sales" | "operatingProfit" | "opMargin" | "per" | "oneYearReturn"
>;

export const valueChainSources = sourcesData as ValueChainSource[];
export const semiconductorTopics = topicsData as ValueChainTopic[];
export const semiconductorLinks = relationsData as ValueChainLink[];
export const valueChainFinancials = financialsData as ValueChainFinancialCache[];
export const valueChainMarketMetrics = marketMetricsData as ValueChainMarketMetricsCache;

const financialMap = new Map(valueChainFinancials.map((item) => [item.companyId, item]));

export const semiconductorCompanies: ValueChainCompany[] = (companiesData as CompanyProfile[]).map((company) => {
  const financial = financialMap.get(company.id);
  return {
    ...company,
    critical: company.critical || undefined,
    ticker: company.ticker || undefined,
    financialAsOf: financial?.asOf,
    financialSourceIds: financial?.sourceIds,
    financialStatus: financial?.status,
    marketCap: financial?.marketCap || undefined,
    sales: financial?.annual.sales || [0, 0, 0],
    operatingProfit: financial?.annual.operatingProfit || [0, 0, 0],
    opMargin: financial?.annual.opMargin || 0,
    per: financial?.annual.per || undefined,
  };
});

export const marketIssueScores = issuesData as ValueChainIssueScore[];

export function issueCompositeScore(issue: ValueChainIssueScore) {
  return issue.composite ?? Math.round(((issue.returnScore + issue.searchScore + issue.volumeScore) / 3) * 10) / 10;
}

export const topMarketIssues = [...marketIssueScores]
  .sort((a, b) => issueCompositeScore(b) - issueCompositeScore(a))
  .slice(0, 20);

export function getCompanyMap() {
  return new Map(semiconductorCompanies.map((company) => [company.id, company]));
}

export function getCompanyFinancial(companyId: string) {
  return financialMap.get(companyId);
}

export function getIssueMetricCache(issueId: string) {
  return valueChainMarketMetrics.issues.find((issue) => issue.issueId === issueId);
}
