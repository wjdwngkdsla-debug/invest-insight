import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const rootDir = path.resolve(path.dirname(__filename), "..");
const dataDir = path.join(rootDir, "data", "value-chain");
const cacheDir = path.join(rootDir, "data", "cache");
const usagePath = path.join(cacheDir, "naver-datalab-usage.json");
const apiUrl = process.env.NAVER_DATALAB_API_URL || "https://naverapihub.apigw.ntruss.com/search-trend/v1/search";
const periods = {
  day: { days: 1, timeUnit: "date" },
  week: { days: 7, timeUnit: "date" },
  month: { days: 35, timeUnit: "week" },
  quarter: { days: 95, timeUnit: "week" },
  half: { days: 185, timeUnit: "month" },
};

function readJson(filePath, fallback = null) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function loadEnvFile(filename) {
  const envPath = path.join(rootDir, filename);
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [key, ...rest] = trimmed.split("=");
    if (!process.env[key]) {
      process.env[key] = rest.join("=").replace(/^["']|["']$/g, "");
    }
  }
}

function dateKey(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function todayKst() {
  const now = new Date();
  return new Date(now.getTime() + 9 * 60 * 60 * 1000);
}

function readUsage() {
  const now = todayKst();
  const month = now.toISOString().slice(0, 7);
  const day = dateKey(now);
  const usage = readJson(usagePath, { month, monthlyCalls: 0, day, dailyCalls: 0 });
  if (usage.month !== month) {
    usage.month = month;
    usage.monthlyCalls = 0;
  }
  if (usage.day !== day) {
    usage.day = day;
    usage.dailyCalls = 0;
  }
  return usage;
}

function assertQuota(usage, callsToAdd) {
  const monthlyLimit = Number(process.env.NAVER_DATALAB_MONTHLY_LIMIT || 30000);
  const dailyLimit = process.env.NAVER_DATALAB_DAILY_LIMIT ? Number(process.env.NAVER_DATALAB_DAILY_LIMIT) : null;
  if (usage.monthlyCalls + callsToAdd > monthlyLimit) {
    throw new Error(`Naver DataLab monthly quota exceeded: ${usage.monthlyCalls}+${callsToAdd}/${monthlyLimit}`);
  }
  if (dailyLimit && usage.dailyCalls + callsToAdd > dailyLimit) {
    throw new Error(`Naver DataLab daily quota exceeded: ${usage.dailyCalls}+${callsToAdd}/${dailyLimit}`);
  }
}

function chunkIssueCompanies(companyIds) {
  if (companyIds.length <= 5) return [companyIds];
  const [anchor, ...rest] = companyIds;
  const chunks = [];
  for (let index = 0; index < rest.length; index += 4) {
    chunks.push([anchor, ...rest.slice(index, index + 4)]);
  }
  return chunks;
}

function average(values) {
  const valid = values.filter((value) => Number.isFinite(value));
  if (!valid.length) return 0;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function normalizeSeries(series, scale) {
  return series.map((point) => ({
    date: point.date,
    value: Math.round(point.value * scale * 10) / 10,
  }));
}

let usage = readUsage();
let usedCalls = 0;

function recordApiCall() {
  usage.monthlyCalls += 1;
  usage.dailyCalls += 1;
  usage.lastRunAt = new Date().toISOString();
  usedCalls += 1;
  writeJson(usagePath, usage);
}

async function requestSearchTrend({ groups, period }) {
  if (!groups.length) return new Map();
  assertQuota(usage, 1);
  const endDate = todayKst();
  const startDate = addDays(endDate, -periods[period].days);
  const body = {
    startDate: formatDate(startDate),
    endDate: formatDate(endDate),
    timeUnit: periods[period].timeUnit,
    keywordGroups: groups.map((group) => ({
      groupName: group.companyId,
      keywords: group.keywords,
    })),
  };

  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-NCP-APIGW-API-KEY-ID": process.env.NAVER_CLIENT_ID,
      "X-NCP-APIGW-API-KEY": process.env.NAVER_CLIENT_SECRET,
    },
    body: JSON.stringify(body),
  });
  recordApiCall();

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Naver DataLab ${response.status}: ${text}`);
  }

  const payload = await response.json();
  return new Map(
    (payload.results || []).map((result) => [
      result.title,
      (result.data || []).map((point) => ({
        date: point.period,
        value: Number(point.ratio || 0),
      })),
    ]),
  );
}

async function fetchIssueSearchSeries({ issue, companiesById, period }) {
  const companyIds = issue.companyIds.filter((id) => companiesById.has(id));
  if (!companyIds.length) return new Map();
  const chunks = chunkIssueCompanies(companyIds);
  const anchorId = companyIds[0];
  let anchorAverage = null;
  const output = new Map();

  for (const chunk of chunks) {
    const groups = chunk.map((companyId) => {
      const company = companiesById.get(companyId);
      return {
        companyId,
        keywords: [company.name],
      };
    });
    const result = await requestSearchTrend({ groups, period });
    const currentAnchorSeries = result.get(anchorId);
    const currentAnchorAverage = currentAnchorSeries ? average(currentAnchorSeries.map((point) => point.value)) : 0;

    if (anchorAverage === null) anchorAverage = currentAnchorAverage || 1;
    const scale = currentAnchorAverage ? anchorAverage / currentAnchorAverage : 1;

    for (const [companyId, series] of result.entries()) {
      if (output.has(companyId)) continue;
      output.set(companyId, normalizeSeries(series, scale));
    }
  }

  return output;
}

function usageCallsNeeded(issues) {
  return issues.reduce((sum, issue) => sum + chunkIssueCompanies(issue.companyIds).length * Object.keys(periods).length, 0);
}

function ensureMetricGroups({ marketMetrics, issues, companiesById }) {
  const groupsByIssue = new Map((marketMetrics.issues || []).map((issue) => [issue.issueId, issue]));

  for (const issue of issues) {
    let group = groupsByIssue.get(issue.id);
    if (!group) {
      group = {
        issueId: issue.id,
        topicId: issue.topicId,
        score: {
          composite: issue.composite || 0,
          returnScore: issue.returnScore || 0,
          searchScore: issue.searchScore || 0,
          tradingValueScore: issue.volumeScore || 0,
        },
        summary: {
          avgReturnPct: issue.avgReturnPct || 0,
          searchChangePct: issue.searchChangePct || 0,
          tradingValueChangePct: issue.volumeChangePct || 0,
        },
        companies: [],
      };
      marketMetrics.issues.push(group);
      groupsByIssue.set(issue.id, group);
    }

    const validCompanyIds = (issue.companyIds || []).filter((companyId) => companiesById.has(companyId));
    group.companies = (group.companies || []).filter((company) => validCompanyIds.includes(company.companyId));
    const metricsByCompany = new Map((group.companies || []).map((company) => [company.companyId, company]));
    for (const companyId of validCompanyIds) {
      const company = companiesById.get(companyId);
      if (!company || metricsByCompany.has(companyId)) continue;
      group.companies.push({
        companyId,
        issueId: issue.id,
        role: company.role || "",
        relation: company.roleDetail || "",
        score: 60,
        week: {
          searchIndex: [],
          tradingValueIndex: [],
          returnPct: 0,
        },
        month: {
          searchIndex: [],
          tradingValueIndex: [],
          returnPct: 0,
        },
        day: {
          searchIndex: [],
          tradingValueIndex: [],
          returnPct: 0,
        },
        quarter: {
          searchIndex: [],
          tradingValueIndex: [],
          returnPct: 0,
        },
        half: {
          searchIndex: [],
          tradingValueIndex: [],
          returnPct: 0,
        },
      });
    }
  }
}

loadEnvFile(".env.local");
loadEnvFile(".env");

const dryRun = process.argv.includes("--dry-run");
const clientId = process.env.NAVER_CLIENT_ID;
const clientSecret = process.env.NAVER_CLIENT_SECRET;
if (!clientId || !clientSecret) {
  // 검색 트렌드는 부가 지표다. 여기서 throw 하면 잡이 죽어 뒤따르는 KRX 거래대금·
  // DART 재무 갱신까지 통째로 건너뛴다. 키가 없으면 이 단계만 건너뛴다.
  console.warn(
    "[naver-datalab] NAVER_CLIENT_ID/NAVER_CLIENT_SECRET missing; skipped search trend cache update",
  );
  process.exit(0);
}

const companies = readJson(path.join(dataDir, "companies.json"), []);
const issues = readJson(path.join(dataDir, "issues.json"), []);
const marketMetrics = readJson(path.join(dataDir, "market-metrics.json"));
const companiesById = new Map(companies.map((company) => [company.id, company]));
ensureMetricGroups({ marketMetrics, issues, companiesById });
const callsNeeded = usageCallsNeeded(issues);
assertQuota(usage, callsNeeded);

if (dryRun) {
  const dailyText = process.env.NAVER_DATALAB_DAILY_LIMIT ? `, daily ${usage.dailyCalls}/${process.env.NAVER_DATALAB_DAILY_LIMIT}` : "";
  console.log(`[naver-datalab] dry-run ok: ${callsNeeded} calls planned, monthly ${usage.monthlyCalls}/${process.env.NAVER_DATALAB_MONTHLY_LIMIT || 30000}${dailyText}`);
  process.exit(0);
}

for (const issue of issues) {
  const metricGroup = marketMetrics.issues.find((item) => item.issueId === issue.id);
  const knownCompanyIds = issue.companyIds.filter((id) => companiesById.has(id));
  if (!knownCompanyIds.length) continue;

  for (const period of Object.keys(periods)) {
    const seriesByCompany = await fetchIssueSearchSeries({ issue, companiesById, period });
    for (const metric of metricGroup.companies) {
      const series = seriesByCompany.get(metric.companyId);
      if (series?.length) {
        metric[period] ||= { searchIndex: [], tradingValueIndex: [], returnPct: 0 };
        metric[period].searchIndex = series;
      }
    }
  }
}

marketMetrics.generatedAt = new Date().toISOString();
marketMetrics.status = "live-cache";
marketMetrics.note = "검색량은 네이버 데이터랩 검색어트렌드 API의 상대지수입니다. 거래대금/수익률/재무는 별도 캐시 수집기로 갱신합니다.";
writeJson(path.join(dataDir, "market-metrics.json"), marketMetrics);

console.log(`[naver-datalab] updated search cache: ${issues.length} issues, ${usedCalls} calls used`);
