/**
 * 관세청 무역통계는 월이 끝나기 전까지는 해당 월 수치가 미완결(중간 집계)이라
 * 급격한 왜곡(꺾임)을 만든다. 그래서 무역 관련 조회는 항상 "지난달"까지만 완결
 * 데이터로 취급하고, 이번 달은 요청 범위에서 제외한다.
 */
export function lastCompletedYymm(): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function yymmMonthsAgo(monthsAgo: number, from = lastCompletedYymm()): string {
  const year = Number(from.slice(0, 4));
  const month = Number(from.slice(4, 6));
  const d = new Date(year, month - 1 - monthsAgo, 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}
