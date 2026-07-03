// 한국은행 ECOS Open API — 한국 기준금리, CPI, 원/달러 환율
const ECOS_BASE = "https://ecos.bok.or.kr/api";

export interface EcosRow {
  TIME: string;
  DATA_VALUE: string;
  ITEM_NAME1?: string;
}

/**
 * ECOS 통계 조회. statCode/itemCode1은 한국은행 100대 통계 코드 참고.
 *  - 기준금리: 722Y001 / 0101000
 *  - 소비자물가지수(CPI): 901Y009 / 0
 *  - 원/달러 환율(매매기준율): 731Y001 / 0000001
 */
export async function fetchEcosStat({
  statCode,
  itemCode1,
  cycle = "Q", // Y/Q/M/D
  startPeriod,
  endPeriod,
  count = 12,
}: {
  statCode: string;
  itemCode1: string;
  cycle?: "Y" | "Q" | "M" | "D";
  startPeriod: string;
  endPeriod: string;
  count?: number;
}): Promise<EcosRow[]> {
  const apiKey = process.env.ECOS_API_KEY;
  if (!apiKey) throw new Error("ECOS_API_KEY가 설정되지 않았습니다.");

  const url = `${ECOS_BASE}/StatisticSearch/${apiKey}/json/kr/1/${count}/${statCode}/${cycle}/${startPeriod}/${endPeriod}/${itemCode1}`;

  const res = await fetch(url, { next: { revalidate: 60 * 60 * 24 } });
  if (!res.ok) {
    throw new Error(`ECOS API 요청 실패 (${statCode}): ${res.status}`);
  }

  const json = await res.json();
  if (json.RESULT?.CODE && json.RESULT.CODE !== "INFO-000") {
    throw new Error(`ECOS API 오류: ${json.RESULT.MESSAGE}`);
  }

  return json.StatisticSearch?.row ?? [];
}
