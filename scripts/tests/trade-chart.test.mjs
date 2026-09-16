import { test } from 'node:test';
import assert from 'node:assert/strict';
import { percentageAxis, percentageLine, percentageY } from '../../lib/trade-chart.ts';

test('percentage scale includes zero and both positive and negative changes', () => {
  const axis = percentageAxis([-25, 10, 56]);
  assert.ok(axis.min <= -25 && axis.max >= 56);
  assert.ok(axis.ticks.includes(0));
  assert.ok(percentageY(56, axis) < percentageY(10, axis));
  assert.ok(percentageY(-25, axis) > percentageY(0, axis));
});

test('percentage line connects changes, not export bar heights', () => {
  const axis = percentageAxis([20, -10, 20]);
  const path = percentageLine([20, -10, 20], axis);
  assert.equal((path.match(/M/g) || []).length, 1);
  assert.equal((path.match(/L/g) || []).length, 2);
  assert.equal(path.split(' ')[0].split(',')[1], path.split(' ')[2].split(',')[1]);
});

test('missing comparisons break the line instead of connecting across gaps', () => {
  const values = [10, null, -20, 0];
  const path = percentageLine(values, percentageAxis(values));
  assert.equal((path.match(/M/g) || []).length, 2);
  assert.equal((path.match(/L/g) || []).length, 1);
});

test('empty, zero and extreme changes produce finite, unclipped coordinates', () => {
  for (const values of [[], [null], [0, 0], [-100, 25000], [.01, .02]]) {
    const axis = percentageAxis(values);
    assert.ok(axis.max > axis.min);
    for (const value of values.filter(v => v !== null)) {
      assert.ok(percentageY(value, axis) >= 10 && percentageY(value, axis) <= 220);
    }
  }
});
