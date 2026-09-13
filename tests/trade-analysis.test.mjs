import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { summarizeTrade, sortTradeCountries, percentagePoints, chartMonthChanges, chartChangeText } from "../lib/trade.ts";
import { overlayPoints, validOverlayDataset } from "../lib/trade-overlay.ts";
import { buildTradeUpdates } from "../lib/trade-updates.ts";

const data = { mode: "live", hs: "test", scope: "all-countries", source: "test", retrievedAt: "2026-03-15", monthlyTotals: { "2026-01": 200, "2026-02": 500 }, rows: [
  { month: "2026-01", country: "US", usd: 100, kg: 10 }, { month: "2026-01", country: "CN", usd: 100, kg: 10 },
  { month: "2026-02", country: "US", usd: 150, kg: 10 }, { month: "2026-02", country: "CN", usd: 350, kg: 10 },
] };
test("bar change dots use the previous calendar month and selected metric", () => {
  const history = [
    { month: "2026-01", value: 100, kg: 10, usdPerKg: 10 },
    { month: "2026-02", value: 200, kg: 40, usdPerKg: 5 },
    { month: "2026-03", value: 0, kg: null, usdPerKg: null },
    { month: "2026-04", value: 20, kg: 2, usdPerKg: 10 },
    { month: "2026-06", value: 30, kg: 2, usdPerKg: 15 },
  ];
  const values = chartMonthChanges(history, "value");
  assert.equal(values.get("2026-01"), null);
  assert.equal(values.get("2026-02"), 100);
  assert.equal(values.get("2026-03"), -100);
  assert.equal(values.get("2026-04"), null);
  assert.equal(values.get("2026-06"), null);
  assert.equal(chartMonthChanges(history, "usdPerKg").get("2026-02"), -50);
  assert.equal(chartChangeText(12.34), "+12.3%");
  assert.equal(chartChangeText(null), "비교자료 없음");
});
test("MoM and share change compare end month, not unequal period totals", () => {
  const all = summarizeTrade(data, "2026-02", "all", "2026-01");
  const us = all.countries.find(c => c.code === "US");
  assert.equal(us.mom, 50); assert.equal(us.shareChange, -20);
  assert.equal(us.share, 250 / 700 * 100);
  assert.equal(percentagePoints(us.shareChange), "-20.0%p");
  assert.equal(percentagePoints(2.34), "+2.3%p");
  assert.equal(percentagePoints(null), "비교자료 없음");
  const country = summarizeTrade(data, "2026-02", "CN");
  assert.deepEqual(country.chart.map(p => p.value), [100, 350]);
  assert.deepEqual(country.chart.map(p => p.usdPerKg), [10, 35]);
});
test("both sorting directions keep missing comparisons at the end", () => {
  const countries = summarizeTrade(data, "2026-02").countries;
  countries.push({ ...countries[0], code: "ZZ", mom: null, shareChange: null });
  assert.deepEqual(sortTradeCountries(countries, "mom", "asc").map(c => c.code), ["US", "CN", "ZZ"]);
  assert.deepEqual(sortTradeCountries(countries, "mom", "desc").map(c => c.code), ["CN", "US", "ZZ"]);
  assert.equal(sortTradeCountries(countries, "shareChange", "desc").at(-1).code, "ZZ");
});
test("overlay quarters only exist at quarter ends, losses stay negative", () => {
  const company = { prices: [{ month: "2026-02", date: "2026-02-27", close: 100 }], quarters: [{ month: "2026-03", period: "2026.1Q", revenue: 2e8, operatingProfit: -1e8, filedAt: "2026-05-15" }] };
  assert.deepEqual(overlayPoints(company, "price", ["2026-01", "2026-02"]).map(p => p.value), [null, 100]);
  assert.deepEqual(overlayPoints(company, "operatingProfit", ["2026-01", "2026-02", "2026-03"]).map(p => p.value), [null, null, -1]);
  assert.equal(overlayPoints(company, "revenue", ["2026-03"])[0].filedAt, "2026-05-15");
  const actual = JSON.parse(fs.readFileSync(new URL("../data/trade/company-history.json", import.meta.url)));
  assert(validOverlayDataset(actual));
  assert.equal(actual.companies.length, 5);
  assert(actual.companies.every(c => c.prices.length === 36 && c.quarters.length > 8));
});
test("notifications deduplicate rechecks but detect new months and corrections", () => {
  const products = [{ id: "test", name: "Test" }];
  const [before] = buildTradeUpdates({ test: data }, products);
  const rechecked = { ...data, retrievedAt: "2026-03-16", rows: [...data.rows].reverse() };
  assert.equal(buildTradeUpdates({ test: rechecked }, products)[0].id, before.id);
  const corrected = structuredClone(data); corrected.rows[0].usd += 1;
  assert.notEqual(buildTradeUpdates({ test: corrected }, products)[0].id, before.id);
  const nextMonth = structuredClone(data); nextMonth.rows.push({ month: "2026-03", country: "US", usd: 400, kg: 10 });
  assert.equal(buildTradeUpdates({ test: nextMonth }, products)[0].month, "2026-03");
  assert.notEqual(buildTradeUpdates({ test: nextMonth }, products)[0].id, before.id);
  assert.equal(buildTradeUpdates({ test: null }, products).length, 0);
});
