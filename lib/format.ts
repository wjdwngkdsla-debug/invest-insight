/** 금액 표기 통일 — "5조 9,972억 원", "2,479억 원", "3.5억 원".
 *
 *  단위 명사 '원'은 한글 맞춤법에 따라 앞말과 띄어 쓴다(억 원 / 조 원).
 *  사이트 전역(종목 상세·IPO 일정·캘린더)이 이 함수 하나를 쓴다.
 */
export function formatKrwEok(won: number, options?: { decimal?: boolean }): string {
  if (!won) return "-";
  const rawEok = won / 1e8;
  // 캘린더의 소액 규모는 소수 첫째 자리까지 보여 준다(10억 미만).
  if (options?.decimal && rawEok < 10) {
    return `${(Math.round(rawEok * 10) / 10).toLocaleString("ko-KR")}억 원`;
  }
  const eok = Math.round(rawEok);
  if (eok >= 10_000) {
    const jo = Math.floor(eok / 10_000);
    const rest = eok % 10_000;
    return rest ? `${jo}조 ${rest.toLocaleString("ko-KR")}억 원` : `${jo}조 원`;
  }
  return `${eok.toLocaleString("ko-KR")}억 원`;
}
