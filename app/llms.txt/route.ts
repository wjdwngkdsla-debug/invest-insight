export const dynamic = "force-static";

export function GET() {
  const body = `# Vericap

Vericap은 IPO 락업 캘린더, IPO 일정, IPO 랭킹, 기관 락업 해제일 등락률, 시장 이슈별 테마맵·관련주 지도를 제공하는 한국 주식 정보 서비스입니다.

## 주요 페이지

- https://vericap.co.kr/ : IPO 락업 해제 캘린더
- https://vericap.co.kr/ipo : IPO 일정
- https://vericap.co.kr/ranking : IPO 랭킹
- https://vericap.co.kr/lockup-ranking : 기관 락업 해제일 등락률
- https://vericap.co.kr/value-chain : 시장 테마맵 · 테마주 관련주 지도
- https://vericap.co.kr/sitemap.xml : 사이트맵

## 데이터 설명

- IPO 락업 데이터는 DART, KRX, 공공데이터포털 자료를 바탕으로 정리합니다.
- 테마맵 데이터는 국내 상장사를 우선으로 표시하며, 네이버 검색어트렌드 상대지수, KRX 거래대금, 기간 수익률, DART 재무 데이터를 캐시로 갱신합니다.
- 모든 정보는 투자 권유가 아니며 최종 투자 판단은 이용자 본인 책임입니다.
`;

  return new Response(body, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}
