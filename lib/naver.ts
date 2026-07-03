import * as cheerio from "cheerio";

// 네이버 금융 — 코스피 외국인 순매수 (투자자별 매매동향)
// 참고: 비공식 크롤링이므로 네이버 페이지 구조 변경 시 셀렉터 수정이 필요할 수 있음
// 한 번의 조회로는 최근 10영업일 정도만 나오기 때문에, 여러 달치를 모으려면
// bizdate를 과거로 이동시키며 여러 페이지를 순차 조회해야 한다.
const NAVER_FOREIGN_URL =
  "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate=";

export interface ForeignNetBuyRow {
  date: string; // YY.MM.DD (네이버 표기 그대로)
  foreignNetBuy: number; // 외국인 순매수 금액(억원)
}

async function fetchForeignNetBuyPage(bizdate: string): Promise<ForeignNetBuyRow[]> {
  const res = await fetch(`${NAVER_FOREIGN_URL}${bizdate}`, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    },
    next: { revalidate: 60 * 60 * 24 },
  });
  if (!res.ok) {
    throw new Error(`네이버 금융 요청 실패: ${res.status}`);
  }

  const html = await res.text();
  const $ = cheerio.load(html);
  const rows: ForeignNetBuyRow[] = [];

  $("table.type_1 tr").each((_, el) => {
    const tds = $(el).find("td");
    if (tds.length < 3) return;

    const date = $(tds[0]).text().trim(); // 예: 26.06.30
    const foreignNetBuyText = $(tds[2]).text().trim().replace(/,/g, "");
    if (!date || !foreignNetBuyText) return;

    const foreignNetBuy = Number(foreignNetBuyText);
    if (Number.isNaN(foreignNetBuy)) return;

    rows.push({ date, foreignNetBuy });
  });

  return rows;
}

function toBizdate(d: Date): string {
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
}

function parseNaverDate(naverDate: string): Date {
  const [yy, mm, dd] = naverDate.split(".").map(Number);
  return new Date(2000 + yy, mm - 1, dd);
}

/**
 * bizdate를 과거로 이동시키며 여러 페이지를 순차 조회해 monthsBack개월치 데이터를 모은다.
 * 네이버 서버 부하를 고려해 최대 페이지 수를 제한한다.
 */
export async function fetchForeignNetBuyHistory(monthsBack = 14): Promise<ForeignNetBuyRow[]> {
  const rows: ForeignNetBuyRow[] = [];
  const seen = new Set<string>();

  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - monthsBack);

  let cursor = new Date();
  const MAX_PAGES = 40; // 안전장치: 과도한 요청 방지

  for (let i = 0; i < MAX_PAGES; i++) {
    const page = await fetchForeignNetBuyPage(toBizdate(cursor));
    if (page.length === 0) break;

    let oldestInPage: Date | null = null;
    for (const row of page) {
      if (!seen.has(row.date)) {
        seen.add(row.date);
        rows.push(row);
      }
      const d = parseNaverDate(row.date);
      if (!oldestInPage || d < oldestInPage) oldestInPage = d;
    }

    if (!oldestInPage || oldestInPage <= cutoff) break;

    cursor = new Date(oldestInPage);
    cursor.setDate(cursor.getDate() - 1);
  }

  return rows;
}
