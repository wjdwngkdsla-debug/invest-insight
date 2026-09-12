export const exportColor = (change: number | null) => change === null || change === 0 ? "#e0e5e8" : change < 0 ? "#d4e3f1" : "#f2d9d7";
export const exportBarColor = (change: number | null, dark = false) => change === null || change === 0
  ? dark ? "#a1aab5" : "#5f6c7b"
  : change < 0 ? dark ? "#76adf4" : "#326db4" : dark ? "#f08b87" : "#b54d48";
// Preserve order while keeping small positive destinations visible; values stay unmodified.
export const exportHeightRatio = (value: number, max: number) => value <= 0 || max <= 0 ? 0 : 0.1 + 0.9 * Math.sqrt(Math.min(1, value / max));
export const inactiveCountryColor = "#e3e8eb";
