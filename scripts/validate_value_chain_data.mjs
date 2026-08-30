import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const rootDir = path.resolve(path.dirname(__filename), "..");
const dataDir = path.join(rootDir, "data", "value-chain");

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(dataDir, name), "utf8"));
}

const sources = readJson("sources.json");
const topics = readJson("topics.json");
const relations = readJson("relations.json");
const companies = readJson("companies.json");
const financials = readJson("financials.json");
const issues = readJson("issues.json");
const marketMetrics = readJson("market-metrics.json");

const sourceIds = new Set(sources.map((source) => source.id));
const topicIds = new Set(topics.map((topic) => topic.id));
const companyIds = new Set(companies.map((company) => company.id));
const financialIds = new Set(financials.map((financial) => financial.companyId));
const issueIds = new Set(issues.map((issue) => issue.id));
const errors = [];
const warnings = [];

function requireRef(condition, message) {
  if (!condition) errors.push(message);
}

function warn(condition, message) {
  if (!condition) warnings.push(message);
}

for (const topic of topics) {
  warn(topic.dataStatus, `topic ${topic.id} has no dataStatus`);
  for (const sourceId of topic.sourceIds || []) {
    requireRef(sourceIds.has(sourceId), `topic ${topic.id} references missing source ${sourceId}`);
  }
  for (const companyId of topic.companyIds || []) {
    requireRef(companyIds.has(companyId), `topic ${topic.id} references missing company ${companyId}`);
  }
}

for (const relation of relations) {
  requireRef(topicIds.has(relation.source), `relation source missing topic ${relation.source}`);
  requireRef(topicIds.has(relation.target), `relation target missing topic ${relation.target}`);
}

for (const company of companies) {
  warn(company.roleDetail, `company ${company.id} has no roleDetail`);
  for (const processId of company.processIds || []) {
    warn(topicIds.has(processId), `company ${company.id} has non-topic process/tag ${processId}`);
  }
  for (const sourceId of company.sourceIds || []) {
    requireRef(sourceIds.has(sourceId), `company ${company.id} references missing source ${sourceId}`);
  }
  warn(financialIds.has(company.id), `company ${company.id} has no financial cache`);
}

for (const financial of financials) {
  requireRef(companyIds.has(financial.companyId), `financial cache references missing company ${financial.companyId}`);
  warn(financial.status, `financial cache ${financial.companyId} has no status`);
  warn(Array.isArray(financial.annual?.sales) && financial.annual.sales.length === 3, `financial cache ${financial.companyId} annual.sales must have 3 years`);
  warn(
    Array.isArray(financial.annual?.operatingProfit) && financial.annual.operatingProfit.length === 3,
    `financial cache ${financial.companyId} annual.operatingProfit must have 3 years`,
  );
}

for (const issue of issues) {
  requireRef(topicIds.has(issue.topicId), `issue ${issue.id} references missing topic ${issue.topicId}`);
  for (const companyId of issue.companyIds || []) {
    requireRef(companyIds.has(companyId), `issue ${issue.id} references missing company ${companyId}`);
  }
  for (const topicId of issue.relatedTopicIds || []) {
    requireRef(topicIds.has(topicId), `issue ${issue.id} references missing related topic ${topicId}`);
  }
}

for (const issueMetric of marketMetrics.issues || []) {
  requireRef(issueIds.has(issueMetric.issueId), `metric cache references missing issue ${issueMetric.issueId}`);
  for (const metric of issueMetric.companies || []) {
    requireRef(companyIds.has(metric.companyId), `metric cache ${issueMetric.issueId} references missing company ${metric.companyId}`);
    for (const period of ["week", "month"]) {
      const item = metric[period];
      warn(item?.searchIndex?.length, `metric ${issueMetric.issueId}/${metric.companyId}/${period} has no searchIndex`);
      warn(item?.tradingValueIndex?.length, `metric ${issueMetric.issueId}/${metric.companyId}/${period} has no tradingValueIndex`);
      warn(typeof item?.returnPct === "number", `metric ${issueMetric.issueId}/${metric.companyId}/${period} has no returnPct`);
    }
  }
}

if (warnings.length) {
  console.log(`[value-chain] warnings ${warnings.length}`);
  warnings.slice(0, 30).forEach((message) => console.log(`- ${message}`));
  if (warnings.length > 30) console.log(`- ...and ${warnings.length - 30} more`);
}

if (errors.length) {
  console.error(`[value-chain] errors ${errors.length}`);
  errors.forEach((message) => console.error(`- ${message}`));
  process.exit(1);
}

console.log(
  `[value-chain] ok: ${topics.length} topics, ${companies.length} companies, ${issues.length} issues, ${financials.length} financial caches, ${
    marketMetrics.issues?.length || 0
  } metric groups`,
);
