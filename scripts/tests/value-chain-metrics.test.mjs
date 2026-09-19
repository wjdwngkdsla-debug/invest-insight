import test from "node:test";
import assert from "node:assert/strict";
import { observedAverage, observedSum, observedReturn, observedPoints } from "../../lib/value-chain-metrics.ts";

test("observed zero differs from missing and legacy example labels", () => {
  assert.equal(observedAverage([{date:"2026-09-18",value:0}]),0);
  assert.equal(observedSum([{date:"2026-09-18",value:0}]),0);
  assert.equal(observedSum([]),null);
  assert.equal(observedAverage([{date:"current",value:60}]),null);
  assert.deepEqual(observedPoints([{date:"2026-09-18",value:NaN}]),[]);
});
test("returns require a source and full period coverage", () => {
  const metric={searchIndex:[],tradingValueIndex:[],returnPct:0,marketSource:"KRX",coverage:{complete:true}};
  assert.equal(observedReturn(metric),0);
  assert.equal(observedReturn({...metric,coverage:{complete:false}}),null);
  assert.equal(observedReturn({...metric,marketSource:undefined}),null);
  assert.equal(observedReturn({...metric,returnPct:null}),null);
});
