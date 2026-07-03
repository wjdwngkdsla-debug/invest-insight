import * as cheerio from "cheerio";

// 관세청_수출입총괄(GW) API — 공공데이터포털
// 참고: 이 API는 XML만 응답하며(type=json 무시됨), 월별 "총괄" 수치만 제공한다.
// 품목별(반도체 등) 세부 데이터는 이 API로는 불가 — 별도 품목별 API 승인 필요.
// 또한 조회기간이 1년 이내로 제한되어 있어, 긴 기간 조회 시 1년 단위로 나눠 합친다.
const CUSTOMS_ENDPOINT = "https://apis.data.go.kr/1220000/Newtrade/getNewtradeList";

export interface CustomsTradeRow {
  period: string; // YYYY-MM
  exportAmount: number; // 수출금액(달러)
  importAmount: number; // 수입금액(달러)
  tradeBalance: number; // 무역수지(달러)
}

async function fetchOneYear(apiKey: string, startYymm: string, endYymm: string): Promise<CustomsTradeRow[]> {
  const params = new URLSearchParams({
    serviceKey: apiKey,
    numOfRows: "200",
    pageNo: "1",
    strtYymm: startYymm,
    endYymm: endYymm,
  });

  const res = await fetch(`${CUSTOMS_ENDPOINT}?${params.toString()}`, {
    next: { revalidate: 60 * 60 * 24 },
  });
  if (!res.ok) {
    throw new Error(`관세청 API 요청 실패: ${res.status}`);
  }

  const xml = await res.text();
  const $ = cheerio.load(xml, { xmlMode: true });

  const resultCode = $("resultCode").first().text();
  if (resultCode && resultCode !== "00") {
    throw new Error(`관세청 API 오류: ${$("resultMsg").first().text()}`);
  }

  const rows: CustomsTradeRow[] = [];
  $("item").each((_, el) => {
    const year = $(el).find("year").text(); // "2025.01"
    rows.push({
      period: year.replace(".", "-"),
      exportAmount: Number($(el).find("expDlr").text()),
      importAmount: Number($(el).find("impDlr").text()),
      tradeBalance: Number($(el).find("balPayments").text()),
    });
  });

  return rows;
}

function addMonths(yymm: string, months: number): string {
  const year = Number(yymm.slice(0, 4));
  const month = Number(yymm.slice(4, 6));
  const d = new Date(year, month - 1 + months, 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export async function fetchCustomsTradeTotal({
  startYymm,
  endYymm,
}: {
  startYymm: string; // YYYYMM
  endYymm: string; // YYYYMM
}): Promise<CustomsTradeRow[]> {
  const apiKey = process.env.DATA_GO_KR_API_KEY;
  if (!apiKey) throw new Error("DATA_GO_KR_API_KEY가 설정되지 않았습니다.");

  // 1년(11개월 폭) 단위 청크로 나눠 순차 조회 후 병합
  const chunks: { start: string; end: string }[] = [];
  let chunkStart = startYymm;
  while (chunkStart <= endYymm) {
    const chunkEnd = addMonths(chunkStart, 11) > endYymm ? endYymm : addMonths(chunkStart, 11);
    chunks.push({ start: chunkStart, end: chunkEnd });
    chunkStart = addMonths(chunkEnd, 1);
  }

  const results = await Promise.all(chunks.map((c) => fetchOneYear(apiKey, c.start, c.end)));
  const rows = results.flat();

  return rows.sort((a, b) => a.period.localeCompare(b.period));
}
