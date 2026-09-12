import test from "node:test";
import assert from "node:assert/strict";
import { exportColor, exportBarColor, exportHeightRatio } from "../components/trade/map-style.ts";

test("visibility correction keeps small exports visible without reversing order", () => {
  const values = [0, 1, 10, 100, 1000, 10000];
  const heights = values.map(v => exportHeightRatio(v, 10000));
  assert.equal(heights[0], 0);
  assert(heights[1] >= 0.1);
  assert.equal(heights.at(-1), 1);
  assert(heights.every((v, i) => !i || v > heights[i - 1]));
  assert.equal(exportHeightRatio(10, 0), 0);
  assert.equal(exportHeightRatio(-1, 10), 0);
  assert.equal(exportHeightRatio(20, 10), 1);
});

test("bar palettes remain significantly darker than matching country fills", () => {
  const luminance = hex => {
    const rgb = hex.slice(1).match(/../g).map(v => parseInt(v, 16) / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  for (const change of [null, -1, 1]) {
    const contrast = (luminance(exportColor(change)) + 0.05) / (luminance(exportBarColor(change)) + 0.05);
    assert(contrast > 3, `Country/bar contrast must exceed 3:1 (${change})`);
  }
});

test("both map themes use red for growth and blue for decline, with neutral unknowns", () => {
  for (const dark of [true, false]) {
    const rgb = value => value.slice(1).match(/../g).map(v => parseInt(v, 16));
    const up = rgb(exportBarColor(12, dark)), down = rgb(exportBarColor(-12, dark));
    assert(up[0] > up[2]);
    assert(down[2] > down[0]);
    assert.equal(exportBarColor(null, dark), exportBarColor(0, dark));
    assert.notEqual(exportBarColor(12, dark), exportBarColor(null, dark));
  }
});
