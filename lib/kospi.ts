// KOSPI 지수 — Yahoo Finance 무료 차트 API (^KS11)
// 참고: 승인받은 KRX Open API "유가증권 일별매매정보"는 개별 종목 시세만 제공하고
// 코스피 지수(합성지수) 자체는 제공하지 않아, 지수값은 Yahoo Finance로 대체합니다.
export interface KospiPoint {
  date: string; // YYYY-MM-DD
  close: number;
}

export async function fetchKospiHistory(range: "1mo" | "6mo" | "2y" = "2y"): Promise<KospiPoint[]> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?range=${range}&interval=1d`;

  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
    next: { revalidate: 60 * 60 * 24 },
  });
  if (!res.ok) {
    throw new Error(`Yahoo Finance 요청 실패: ${res.status}`);
  }

  const json = await res.json();
  const result = json?.chart?.result?.[0];
  const timestamps: number[] = result?.timestamp ?? [];
  const closes: number[] = result?.indicators?.quote?.[0]?.close ?? [];

  return timestamps
    .map((ts, i) => ({
      date: new Date(ts * 1000).toISOString().slice(0, 10),
      close: closes[i],
    }))
    .filter((p) => typeof p.close === "number");
}
