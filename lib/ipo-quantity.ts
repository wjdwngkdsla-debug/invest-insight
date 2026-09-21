export function ipoQuantity(tier?: { qty?: number | null; source?: string }): number | null {
  if (tier?.source === "zero_missing" || typeof tier?.qty !== "number") return null;
  return Number.isSafeInteger(tier.qty) && tier.qty >= 0 ? tier.qty : null;
}
