export function percentageAxis(values: (number | null)[]) {
  const finite = values.filter((value): value is number => value !== null && Number.isFinite(value));
  const low = Math.min(0, ...finite);
  const high = Math.max(0, ...finite);
  const span = high - low || 20;
  const base = 10 ** Math.floor(Math.log10(span / 4));
  const step = [1, 2, 5, 10].map(n => n * base).find(n => n >= span / 4)!;
  const min = low === high ? -10 : Math.floor(low / step) * step;
  const max = low === high ? 10 : Math.ceil(high / step) * step;
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, i) => Number((min + i * step).toPrecision(12)));
  return { min, max, ticks };
}

export function percentageY(value: number, axis: { min: number; max: number }) {
  return 220 - (value - axis.min) / (axis.max - axis.min) * 210;
}

export function percentageLine(values: (number | null)[], axis: { min: number; max: number }) {
  let connected = false;
  return values.map((value, i) => {
    if (value === null || !Number.isFinite(value)) {
      connected = false;
      return "";
    }
    const command = connected ? "L" : "M";
    connected = true;
    return `${command}${(i + .5) / values.length * 1000},${percentageY(value, axis)}`;
  }).filter(Boolean).join(" ");
}
