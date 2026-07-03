// 억 단위(1e8) 변환 — 큰 달러/원화 금액을 한국식으로 보기 쉽게 표시할 때 사용
export function toEok(value: number): number {
  return Math.round((value / 1e8) * 100) / 100;
}

export function formatNumber(value: number): string {
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}
