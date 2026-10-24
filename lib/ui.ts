/** 화면 전반에서 되풀이되는 표현을 한곳에 모은다.
 *
 *  카드 그림자와 등락 색상은 지금까지 파일마다 길게 다시 적혀 있었다.
 *  같은 모양을 손보려면 다섯 군데를 동시에 고쳐야 했고, 실제로 모서리 반경이
 *  18·20·24·26·28·30·32·34px으로 제각각 갈라져 있었다.
 */

/** 카드 공통 그림자 — 아래로 아주 옅게 깔리는 그림자 하나만 쓴다. */
export const CARD_SHADOW = "shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)]";

/** 기본 카드 (표·패널). */
export const CARD = `rounded-[20px] border border-gray-200 bg-white ${CARD_SHADOW}`;

/** 좁은 화면용 카드 — 모바일에서 한 단계 작은 반경을 쓴다. */
export const CARD_SM = `rounded-[18px] border border-gray-200 bg-white ${CARD_SHADOW} sm:rounded-[20px]`;

/** 종목 상세 상단처럼 넓게 자리잡는 영역. */
export const CARD_HERO = `rounded-[24px] border border-gray-200 bg-white ${CARD_SHADOW} md:rounded-[26px]`;

/** 한국 증시 관례 — 상승은 빨강, 하락은 파랑. 미국과 반대라 헷갈리기 쉽다. */
export const UP_TONE = "text-rose-600";
export const DOWN_TONE = "text-blue-600";

export function returnTone(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return "text-slate-300";
  return pct >= 0 ? UP_TONE : DOWN_TONE;
}

/** 부호를 붙인 퍼센트 문자열. 양수에 '+'를 붙이는 규칙을 한곳에서 지킨다. */
export function signedPct(pct: number, digits = 1): string {
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}
