import test from "node:test";
import assert from "node:assert/strict";
import { ipoQuantity } from "../../lib/ipo-quantity.ts";

test("IPO quantities distinguish confirmed zero from missing and invalid data", () => {
  assert.equal(ipoQuantity({ qty: 0 }), 0);
  assert.equal(ipoQuantity({ qty: 10, source: "dart_table" }), 10);
  for (const tier of [undefined, {}, { qty: null }, { qty: 0, source: "zero_missing" }, { qty: -1 }, { qty: NaN }, { qty: 1.5 }]) {
    assert.equal(ipoQuantity(tier), null);
  }
});
