// 관세청_품목별 국가별 수출입실적(GW) API — 공공데이터포털
// 조회기간 1년 제한 있음 (Newtrade와 동일)
const ITEMTRADE_ENDPOINT = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList";

// "반도체"는 HS 8541(다이오드/트랜지스터)과 8542(집적회로, DRAM/NAND 메모리 포함) 전체를 합산해야 한다.
// 이전 버전은 8542311000(마이크로프로세서 계열) 단일 코드만 잡아서 메모리 반도체(854232xx, 한국 반도체
// 수출의 절대 비중)를 통째로 누락했었다. hsSgn을 지정하지 않으면 국가별 전체 품목이 반환되므로,
// 여기서 8541/8542로 시작하는 품목만 걸러 합산한다.
const SEMICONDUCTOR_HS_PREFIXES = ["8541", "8542"];
const MAJOR_TRADE_PARTNERS = ["US", "CN", "JP", "VN", "HK", "TW", "EU"];

export interface ItemTradeRow {
  period: string; // YYYY-MM
  exportAmount: number; // 수출금액(달러)
}

function addMonths(yymm: string, months: number): string {
  const year = Number(yymm.slice(0, 4));
  const month = Number(yymm.slice(4, 6));
  const d = new Date(year, month - 1 + months, 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function extractTag(itemXml: string, tag: string): string {
  const match = itemXml.match(new RegExp(`<${tag}>([^<]*)</${tag}>`));
  return match ? match[1] : "";
}

async function fetchOneYearOneCountry(
  apiKey: string,
  startYymm: string,
  endYymm: string,
  cntyCd: string
): Promise<ItemTradeRow[]> {
  const params = new URLSearchParams({
    serviceKey: apiKey,
    strtYymm: startYymm,
    endYymm: endYymm,
    cntyCd,
  });

  const res = await fetch(`${ITEMTRADE_ENDPOINT}?${params.toString()}`, {
    next: { revalidate: 60 * 60 * 24 },
  });
  if (!res.ok) {
    throw new Error(`관세청 품목별 API 요청 실패: ${res.status}`);
  }

  const xml = await res.text();

  if (xml.includes("<resultCode>") && !xml.includes("<resultCode>00</resultCode>")) {
    const msgMatch = xml.match(/<resultMsg>([^<]*)<\/resultMsg>/);
    throw new Error(`관세청 품목별 API 오류: ${msgMatch?.[1] ?? "알 수 없는 오류"}`);
  }

  const rows: ItemTradeRow[] = [];
  const itemBlocks = xml.match(/<item>[\s\S]*?<\/item>/g) ?? [];

  const byMonth = new Map<string, number>();
  for (const block of itemBlocks) {
    const hsCd = extractTag(block, "hsCd");
    if (!SEMICONDUCTOR_HS_PREFIXES.some((prefix) => hsCd.startsWith(prefix))) continue;

    const year = extractTag(block, "year"); // "2025.01"
    if (year === "총계" || !year) continue;

    const expDlr = Number(extractTag(block, "expDlr"));
    const period = year.replace(".", "-");
    byMonth.set(period, (byMonth.get(period) ?? 0) + expDlr);
  }

  for (const [period, exportAmount] of byMonth) {
    rows.push({ period, exportAmount });
  }

  return rows;
}

/**
 * 반도체(HS 8541+8542 전체) 월별 수출액 합계를 가져온다.
 * cntyCd가 필수라 전세계 합산이 불가능해, 주요 교역국(미·중·일·베트남·홍콩·대만·EU)을
 * 합산하는 근사치로 계산한다. 실제 전체 수출액보다는 다소 작게 잡힐 수 있다.
 */
export async function fetchSemiconductorExports({
  startYymm,
  endYymm,
}: {
  startYymm: string;
  endYymm: string;
}): Promise<ItemTradeRow[]> {
  const apiKey = process.env.DATA_GO_KR_API_KEY;
  if (!apiKey) throw new Error("DATA_GO_KR_API_KEY가 설정되지 않았습니다.");

  const chunks: { start: string; end: string }[] = [];
  let chunkStart = startYymm;
  while (chunkStart <= endYymm) {
    const chunkEnd = addMonths(chunkStart, 11) > endYymm ? endYymm : addMonths(chunkStart, 11);
    chunks.push({ start: chunkStart, end: chunkEnd });
    chunkStart = addMonths(chunkEnd, 1);
  }

  const results = await Promise.all(
    MAJOR_TRADE_PARTNERS.flatMap((cntyCd) =>
      chunks.map((c) => fetchOneYearOneCountry(apiKey, c.start, c.end, cntyCd))
    )
  );

  const byMonth = new Map<string, number>();
  for (const rows of results) {
    for (const row of rows) {
      byMonth.set(row.period, (byMonth.get(row.period) ?? 0) + row.exportAmount);
    }
  }

  return Array.from(byMonth.entries())
    .map(([period, exportAmount]) => ({ period, exportAmount }))
    .sort((a, b) => a.period.localeCompare(b.period));
}
