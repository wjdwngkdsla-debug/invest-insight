# Vericap (invest-insight) — 작업 인수인계 문서

## 프로젝트 개요
공공 API 기반 매크로 경제 인사이트 대시보드. Next.js 16(App Router) + Tailwind v4 + Recharts.
다크(#141414) 베이스 + 라임그린(#2BEE34) 포인트 컬러 디자인.

## 실행 방법
```
cd invest-insight
npm install
npm run dev
```
`http://localhost:3000` 접속.

⚠️ **중요**: 프로젝트 경로에 한글이 들어가면 Turbopack이 크래시합니다(byte-boundary 버그).
반드시 `C:\dev\invest-insight` 같은 영문 경로에 두세요.

## API 키 (.env.local에 필요, 새 컴퓨터에서 직접 발급받거나 기존 값 복사)
```
ECOS_API_KEY=한국은행 ECOS
DATA_GO_KR_API_KEY=공공데이터포털 (관세청 API 2개: 수출입총괄 + 품목별국가별실적)
FRED_API_KEY=FRED(세인트루이스 연은)
KRX_API_KEY=KRX Open API (현재는 실사용 안 함, KOSPI는 Yahoo Finance로 대체)
```
`.env.local`은 `.gitignore` 처리되어 있어 커밋되지 않음 — 새 컴퓨터로 옮길 때 파일 자체를 복사해야 함.

## 폴더 구조
```
app/
  page.tsx              홈 (카드 그리드 랜딩)
  rates/                기준금리 챕터
  cpi/                  CPI 챕터
  semiconductor-kospi/  반도체↔KOSPI 챕터
  fx-export/            환율↔수출액 챕터
  trade-foreign/        무역수지↔외국인순매수 챕터
  oil-cpi/              유가↔CPI 챕터
  api/                  위 6개에 대응하는 API 라우트 (JSON 반환)
components/
  ChapterPage.tsx        각 챕터 공용 레이아웃(뒤로가기+제목+톤)
  CountryIndicatorCard.tsx  다국가 비교 차트+표 (금리/CPI에서 재사용)
  DualAxisChart.tsx      이중축 상관관계 차트 (반도체/환율/무역/유가에서 재사용)
  FxExportChart.tsx      환율 페이지 전용 (4통화 등락률 + 수출액)
lib/
  ecos.ts, fred.ts, customs.ts, itemtrade.ts, naver.ts, kospi.ts, fx.ts
  각 데이터 소스별 fetch 함수
  rates.ts, cpi.ts, semiKospi.ts, fxExport.ts, tradeForeign.ts, oilCpi.ts
  각 챕터의 데이터 조합/가공 로직
  quarterly.ts   여러 국가를 같은 분기축으로 정렬 + 추정치 계산 (핵심 로직)
  dateUtils.ts   "이번 달은 미완결이니 제외" 공통 유틸
  format.ts      억 단위 변환 + 콤마 포맷
  types.ts       공용 타입
```

## 데이터 소스 요약
| 챕터 | 소스 | 비고 |
|---|---|---|
| 기준금리 | ECOS(한국) + FRED(미/일/유/중) | 5개국 공통 분기축 정렬 |
| CPI | ECOS(한국) + FRED(미/유) | 일본/중국은 FRED 공급 지연이 심해 별도 축으로 분리 표시 |
| 반도체↔KOSPI | 관세청 품목별API(nitemtrade, HS 8541+8542 합산) + Yahoo Finance(KOSPI) | cntyCd 필수라 주요 7개국(US,CN,JP,VN,HK,TW,EU) 합산 근사치 |
| 환율↔수출액 | 관세청 총괄API(Newtrade) + ECOS(4통화 환율) | 환율은 등락률(%)로 표시, 툴팁에 실제값 |
| 무역수지↔외국인순매수 | 관세청 총괄API + 네이버 금융 크롤링(비공식) | 네이버는 페이지네이션으로 최근 14개월치 수집 |
| 유가↔CPI | FRED(WTI) + ECOS(한국CPI) + FRED(미국CPI) | 인위적 시차 이동 없이 실제 관측월 그대로 |

## 알려진 제약/이슈
1. **반도체 수출액**은 관세청 API의 `cntyCd` 필수 제약 때문에 "전세계 합계"가 아니라 주요 7개국 합산 근사치. 실제보다 다소 작을 수 있음.
2. **네이버 외국인 순매수 크롤링**은 비공식이라 네이버 페이지 구조 바뀌면 셀렉터(`table.type_1`) 깨질 수 있음.
3. **일본 CPI**는 FRED 공급이 2021-06 이후 완전히 끊김(placeholder "." 값). **중국 CPI**는 2025-04 이후 갱신 중단. 둘 다 공통 축에서 빼고 자체 최신 시점으로 별도 표시 중.
4. 매일 배치 갱신 전제 (`revalidate: 86400`)이지만 아직 Vercel Cron 등 스케줄러는 연결 안 함 — 지금은 페이지 요청 시 24시간 캐시로만 동작.

## 디자인 시스템
- 배경(다크): `#141414`
- 포인트(라임): `#2BEE34`
- 카드: `#1e1e1e` bg, `#2a2a2a` border, `rounded-[18px]`
- 카테고리 배지: 라임 배경 필(pill) + 진한 그린 텍스트(`--color-lime-ink: #0f2b12`)
- 서브페이지(챕터 상세)는 기존 Apple 스타일(라이트/파치먼트/다크 교차) 유지 중 — 필요시 홈과 통일할지 결정 필요

## 다음에 할 일 후보 (미정, 우선순위 상의 필요)
- [ ] 챕터 상세 페이지도 다크+라임 테마로 통일할지 결정
- [ ] Vercel 배포 (지금은 로컬 전용)
- [ ] 반도체 수출액 "전세계 합계" 정확도 개선 방법 검토
- [ ] 네이버 크롤링 대체 공식 소스 검토
- [ ] 배치 스케줄러(Vercel Cron) 연결

## 집에서 이어서 작업할 때 Claude에게 줄 프롬프트 (복사해서 붙여넣기)
```
C:\dev\invest-insight 프로젝트(Next.js, 다크+라임그린 디자인) 이어서 작업할 거야.
HANDOFF.md 파일 먼저 읽고 전체 구조/이슈 파악해줘.
그다음 [여기에 오늘 하고 싶은 작업 적기] 진행해줘.
```
