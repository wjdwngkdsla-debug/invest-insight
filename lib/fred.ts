// FRED(미국 세인트루이스 연은) API — 미국/일본/유럽/중국 금리·CPI·유가 시계열 공용 클라이언트
const FRED_BASE = "https://api.stlouisfed.org/fred/series/observations";

export interface FredObservation {
  date: string;
  value: string;
}

/**
 * FRED 시계열 시리즈 ID로 관측치를 가져온다.
 * 대표 시리즈 ID:
 *  - 미국 기준금리: DFEDTARU (상단) / FEDFUNDS (실효금리, 월별)
 *  - 일본 기준금리: IRSTCB01JPM156N
 *  - 유럽 기준금리: ECBDFR
 *  - 중국 기준금리: INTDSRCNM193N (참고용, 갱신 주기 낮음)
 *  - 미국 CPI(YoY): CPIAUCSL (지수, YoY는 직접 계산)
 *  - 일본 CPI: JPNCPIALLMINMEI
 *  - 유럽 CPI: CP0000EZ19M086NEST
 *  - 중국 CPI: CHNCPIALLMINMEI
 *  - WTI 유가: DCOILWTICO
 */
export async function fetchFredSeries(
  seriesId: string,
  { limit = 40 }: { limit?: number } = {}
): Promise<FredObservation[]> {
  const apiKey = process.env.FRED_API_KEY;
  if (!apiKey) throw new Error("FRED_API_KEY가 설정되지 않았습니다.");

  const url = `${FRED_BASE}?series_id=${seriesId}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=${limit}`;

  const res = await fetch(url, { next: { revalidate: 60 * 60 * 24 } });
  if (!res.ok) {
    throw new Error(`FRED API 요청 실패 (${seriesId}): ${res.status}`);
  }

  const json = await res.json();
  const observations: FredObservation[] = json.observations ?? [];
  return observations.reverse(); // 오래된 순으로 정렬
}
