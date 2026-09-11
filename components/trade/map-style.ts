export const exportColor = (change: number | null) => change === null ? "#d9d1eb" : change < 0 ? "#f2c6bf" : "#b8dce9";
export const exportBarColor = (change: number | null) => change === null ? "#665099" : change < 0 ? "#af423a" : "#126487";
// Preserve order while keeping small positive destinations visible; values stay unmodified.
export const exportHeightRatio = (value: number, max: number) => value <= 0 || max <= 0 ? 0 : 0.1 + 0.9 * Math.sqrt(Math.min(1, value / max));
export const inactiveCountryColor = "#e3e8eb";
export const originColor = "#655bd6";
export const referenceBarColor = (value: number, max: number) => {
  const t = Math.min(1, value / Math.max(1, max));
  return `rgb(${Math.round(200 + t * 55)},${Math.round(255 - t * 80)},${Math.round(t * 20)})`;
};
export const flatBarColor = (value: number, max: number, dark: boolean) => {
  if (dark) return referenceBarColor(value, max);
  const t = Math.min(1, value / Math.max(1, max));
  return `rgb(${Math.round(25 + t * 164)},${Math.round(122 - t * 34)},${Math.round(141 - t * 105)})`;
};
