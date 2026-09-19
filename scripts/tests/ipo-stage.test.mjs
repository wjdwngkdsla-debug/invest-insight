import test from "node:test";
import assert from "node:assert/strict";
import { compareIpoStages, ipoStageStatus, ipoToday, matchesIpoStage } from "../../lib/ipo-stage.ts";

const today = "2026-09-20";
const base = { name: "진코스텍", corp_code: "test", stock_code: "272290" };
const status = fields => ipoStageStatus({ ...base, ...fields }, today);

test("unknown and pre-forecast schedules share one upcoming label", () => {
  assert.deepEqual(status({}), { stage: "upcoming", label: "공모예정" });
  assert.deepEqual(status({ forecast_start: "2026-09-21", sub_start: "2026-10-01", listing_date: "2026-10-10" }), { stage: "upcoming", label: "공모예정" });
});

test("active forecast and subscription override future listing announcements", () => {
  assert.equal(status({ forecast_start: today, forecast_end: today, listing_date: "2026-10-10" }).label, "수요예측");
  assert.equal(status({ sub_start: "2026-09-19", sub_end: today, listing_date: "2026-10-10" }).label, "청약");
});

test("forecast-to-subscription gap is explicitly pending", () => {
  assert.deepEqual(status({ forecast_end: "2026-09-19" }), { stage: "subscription", label: "청약 예정" });
  assert.equal(status({ sub_start: "2026-09-21" }).label, "청약 예정");
});

test("completed subscription stays in listing even without a listing date", () => {
  assert.deepEqual(status({ sub_end: "2026-09-19" }), { stage: "listing", label: "상장일 미정" });
  assert.equal(status({ sub_end: "2026-09-19", listing_date: "2026-09-22" }).label, "상장 예정 D-2");
  assert.equal(status({ listing_date: today }).label, "상장일");
  assert.equal(status({ listing_date: "2026-09-19" }).stage, "listed");
});

test("withdrawals move to history, with priority over every schedule", () => {
  const item = { ...base, withdrawn: true, sub_start: today, listing_date: today };
  assert.equal(ipoStageStatus(item, today).label, "공모 철회");
  assert.equal(matchesIpoStage(item, "", "all", today, false), false);
  assert.equal(matchesIpoStage(item, "", "all", today, true), true);
});

test("search combines with stage, all resets stage, hidden and archive stay separated", () => {
  const item = { ...base, forecast_start: today, forecast_end: today };
  assert.equal(matchesIpoStage(item, "진 코스텍", "forecast", today, false), true);
  assert.equal(matchesIpoStage(item, "272290", "all", today, false), true);
  assert.equal(matchesIpoStage(item, "", "listing", today, false), false);
  assert.equal(matchesIpoStage(item, "", "all", today, false, true), false);
  assert.equal(matchesIpoStage(item, "", "all", today, true, true), true);
  for (const flag of ["review_pending", "fixed_excluded", "management_hidden", "schedule_hidden"]) {
    assert.equal(matchesIpoStage({ ...item, [flag]: true }, "", "all", today, true, true), false);
  }
});

test("calendar transitions use Korea time", () => {
  assert.equal(ipoToday(new Date("2026-09-19T15:00:00Z")), today);
  assert.equal(ipoToday(new Date("2026-09-19T14:59:59Z")), "2026-09-19");
});

test("listing without a date remains ahead of subscription, forecast and upcoming", () => {
  const items = [
    { ...base, name: "upcoming", forecast_start: "2026-09-25" },
    { ...base, name: "forecast", forecast_start: today, forecast_end: today },
    { ...base, name: "subscription", sub_start: today, sub_end: today },
    { ...base, name: "listing-unknown", sub_end: "2026-09-19" },
    { ...base, name: "listing-later", listing_date: "2026-09-24" },
    { ...base, name: "listing-today", listing_date: today },
  ];
  assert.deepEqual(items.sort((a, b) => compareIpoStages(a, b, today)).map(item => item.name),
    ["listing-today", "listing-later", "listing-unknown", "subscription", "forecast", "upcoming"]);
});

test("history sorts newest events first across both stored date formats", () => {
  const a = { ...base, withdrawn: true, withdrawn_date: "20260919" };
  const b = { ...base, listing_date: "2026-09-18" };
  assert.ok(compareIpoStages(a, b, today, true) < 0);
});
