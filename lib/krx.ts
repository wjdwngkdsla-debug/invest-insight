// KRX Open API (openapi.krx.co.kr) — 유가증권 일별매매정보 (KOSPI 지수)
const KRX_ENDPOINT =
  "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"; // 유가증권 일별매매정보

export interface KrxDailyRow {
  date: string; // BAS_DD
  closeIndex: number; // TDD_CLSPRC (지수 종목이면 종가)
  changeRate: number;
}

export async function fetchKospiDaily(basDd: string): Promise<KrxDailyRow[]> {
  const apiKey = process.env.KRX_API_KEY;
  if (!apiKey) throw new Error("KRX_API_KEY가 설정되지 않았습니다.");

  const res = await fetch(`${KRX_ENDPOINT}?basDd=${basDd}`, {
    headers: { AUTH_KEY: apiKey },
    next: { revalidate: 60 * 60 * 24 },
  });
  if (!res.ok) {
    throw new Error(`KRX API 요청 실패: ${res.status}`);
  }

  const json = await res.json();
  const rows = json?.OutBlock_1 ?? [];
  return rows.map((row: Record<string, string>) => ({
    date: row.BAS_DD,
    closeIndex: Number(row.TDD_CLSPRC),
    changeRate: Number(row.FLUC_RT),
  }));
}
