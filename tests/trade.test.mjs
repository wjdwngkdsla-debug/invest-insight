import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { growth, priorMonth, summarizeTrade, validTradeDataset, unitValue, usdText, tradeMonths } from "../lib/trade.ts";

test("unit export values use aggregate net kilograms and handle missing weights", () => {
  assert.equal(unitValue(100, 0), null);
  assert.equal(unitValue(100, null), null);
  assert.equal(unitValue(120, 4), 30);
  for (const id of ["dram", "beauty", "transformer"]) {
    const data = JSON.parse(fs.readFileSync(new URL("../data/trade/" + id + ".json", import.meta.url)));
    for (const [month, kg] of Object.entries(data.monthlyWeightTotals)) {
      const result = summarizeTrade(data, month);
      assert.equal(result.kg, kg);
      assert.equal(result.usdPerKg, data.monthlyTotals[month] / kg);
    }
    const broken = structuredClone(data);
    broken.rows[0].kg = -1;
    assert.equal(validTradeDataset(broken, broken.hs), false);
  }
  assert.equal(usdText(99999999), "1억 달러");
  assert.equal(usdText(123), "123 달러");
});

test("year boundaries and zero baselines do not produce fabricated growth", () => {
  assert.equal(priorMonth("2026-01", 2), "2025-11");
  assert.equal(growth(10, 0), null);
  assert.equal(growth(150, 100), 50);
});

test("all-country totals and metadata include every API destination", () => {
  for (const id of ["dram", "beauty", "transformer"]) {
    const data = JSON.parse(fs.readFileSync(new URL("../data/trade/" + id + ".json", import.meta.url)));
    assert.equal(data.scope, "all-countries");
    assert(validTradeDataset(data, data.hs));
    assert(data.countryCodes.length > (id === "beauty" ? 190 : 40));
    for (const [month, total] of Object.entries(data.monthlyTotals)) {
      const summary = summarizeTrade(data, month);
      assert.equal(summary.now, total);
      assert.equal(summary.countries.length, data.rows.filter(r => r.month === month).length);
      assert.equal(summary.countries.reduce((n, c) => n + c.usd, 0), total);
    }
    const broken = { ...data, rows: data.rows.slice(1) };
    assert.equal(validTradeDataset(broken, data.hs), false);
  }
});

test("missing country observations cannot masquerade as a full aggregate", () => {
  const data = { mode: "live", hs: "8542321010", source: "test", countryCodes: ["US", "CN"], rows: [
    { month: "2026-07", country: "US", usd: 100 },
    { month: "2026-06", country: "US", usd: 75 },
    { month: "2026-06", country: "CN", usd: 25 },
  ] };
  assert.equal(summarizeTrade(data, "2026-07").now, null);
  assert.equal(summarizeTrade(data, "2026-07").countries[0].share, null);
  assert.equal(summarizeTrade(data, "2026-07", "US").now, 100);
});

test("cache rejects duplicates, non-numeric values, synthetic data, and wrong HS codes", () => {
  const data = { mode: "live", hs: "3304999000", source: "test", rows: [{ month: "2026-07", country: "TH", usd: 0 }] };
  assert.equal(validTradeDataset(data, data.hs), true);
  assert.equal(validTradeDataset(data, "8542321010"), false);
  assert.equal(validTradeDataset({ ...data, rows: [...data.rows, ...data.rows] }, data.hs), false);
  assert.equal(validTradeDataset({ ...data, mode: "sample" }, data.hs), false);
  assert.equal(validTradeDataset({ ...data, rows: [{ ...data.rows[0], usd: NaN }] }, data.hs), false);
});

test("three month growth uses sums and does not replace missing months with zero", () => {
  const data = { mode: "live", hs: "8542321010", source: "test", rows: [
    ["2026-05", 100], ["2026-06", 200], ["2026-07", 300],
    ["2025-05", 100], ["2025-06", 100], ["2025-07", 100],
  ].map(([month, usd]) => ({ month, usd, country: "US" })) };
  const summary = summarizeTrade(data, "2026-07", "US");
  assert.equal(summary.now, 300);
  assert.equal(summary.yoy, 200);
  assert.equal(summary.recent, 600);
  assert.equal(summary.recentGrowth, 100);
  assert.equal(summarizeTrade({...data, rows: data.rows.filter(r => r.month !== "2025-06")}, "2026-07").recentGrowth, null);
});

test("country filter and share denominator use the same reporting month", () => {
  const data = { mode: "live", hs: "8542321010", source: "test", rows: [
    { month: "2026-07", country: "US", usd: 75 },
    { month: "2026-07", country: "CN", usd: 25 },
    { month: "2026-06", country: "US", usd: 900 },
  ] };
  assert.equal(summarizeTrade(data, "2026-07").now, 100);
  assert.equal(summarizeTrade(data, "2026-07", "US").now, 75);
  assert.equal(summarizeTrade(data, "2026-07").countries[0].share, 75);
});

test("inclusive month ranges sum amounts and weights before calculating growth or unit value", () => {
  assert.deepEqual(tradeMonths("2025-12", "2026-02"), ["2025-12", "2026-01", "2026-02"]);
  assert.throws(() => tradeMonths("2026-05", "2026-04"), RangeError);
  assert.throws(() => tradeMonths("2026-13", "2026-14"), RangeError);
  const data = { mode: "live", hs: "test", source: "test", scope: "all-countries", rows: [
    ["2025-04", "US", 100, 10], ["2025-05", "US", 300, 10],
    ["2026-04", "US", 200, 10], ["2026-05", "US", 600, 30],
    ["2026-04", "CN", 100, 20],
  ].map(([month, country, usd, kg]) => ({ month, country, usd, kg })),
    monthlyTotals: { "2025-04": 100, "2025-05": 300, "2026-04": 300, "2026-05": 600 },
    monthlyWeightTotals: { "2025-04": 10, "2025-05": 10, "2026-04": 30, "2026-05": 30 } };
  const all = summarizeTrade(data, "2026-05", "all", "2026-04");
  assert.equal(all.now, 900);
  assert.equal(all.kg, 60);
  assert.equal(all.usdPerKg, 15);
  assert.equal(all.yoy, 125);
  const us = summarizeTrade(data, "2026-05", "US", "2026-04");
  assert.equal(us.now, 800);
  assert.equal(us.usdPerKg, 20);
  assert.equal(us.yoy, 100);
  assert.equal(all.countries.find(c => c.code === "US").share, 800 / 900 * 100);
  const cn = all.countries.find(c => c.code === "CN");
  assert.equal(cn.usd, 100);
  assert.equal(cn.change, null);
  assert.equal(summarizeTrade(data, "2026-05", "all", "2026-03").now, null);
  assert.equal(summarizeTrade(data, "2026-05", "CN", "2026-03").now, null);
  assert.deepEqual(summarizeTrade(data, "2026-05"), summarizeTrade(data, "2026-05", "all", "2026-05"));
});
