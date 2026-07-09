# 운영 방법

## 자동 갱신

- GitHub Actions가 매일 한국시간 00:00에 실행됩니다.
- **편입 대상은 시트의 `IPO종목` 탭이 유일한 기준**입니다 (KRX 연간 스캔은 폐기).
  새 종목은 `구분(시장)/회사명/상장일/종목코드` 한 줄을 추가하면 다음 배치에서 편입됩니다.
  회사명은 DART 공시 회사명과 같아야 파싱이 됩니다.
- Google Sheet의 수동 수정값·수기입력·휴장일도 함께 내려받습니다.
- 신규 종목만 DART 파싱하고, 기존 종목은 금융위 API 검증과 종가 갱신만 수행합니다.
- `data/site_data.json`과 운영 CSV를 갱신하고 Google Sheet를 다시 올린 뒤 GitHub에 자동 커밋합니다.
- GitHub 커밋이 생기면 Vercel이 홈페이지를 자동 재배포합니다.

## Google Sheet에서 수정할 칸

`운영_락업일정` 탭에서 아래 네 칸만 수정하면 됩니다.

| 한글 헤더 | 입력 방법 |
|---|---|
| 수동값사용(Y/N) | 수동값을 홈페이지에 반영하려면 `Y`, 자동값을 쓰려면 `N` |
| 수동해제일 | `YYYY-MM-DD` 형식 |
| 수동물량 | 쉼표 없이 숫자 입력 |
| 운영자메모 | 수정 이유 또는 확인 내용 |

수정 후 GitHub의 `Actions` → `Update lockup data` → `Run workflow`를 누르면 자정 전에도 즉시 반영할 수 있습니다.

## 수기입력 탭 (자동 파싱이 안 되는 종목 직접 추가)

스팩합병·이전상장 등 DART 자동 파싱이 안 되는 종목의 락업 이벤트는 `수기입력` 탭에 직접 추가합니다.
아래 다섯 칸이 전부 필수이고, 나머지(종목명·시장·상장주식수·종가·비중·상태)는 배치가 KRX에서 자동으로 채웁니다.

| 컬럼 | 입력 방법 |
|---|---|
| 종목코드 | 6자리 코드 (예: `0017J0`) |
| 구분 | `IPO기관` 또는 `기존주주` (드롭다운) |
| 락업기간 | 예: `6개월`, `1년` |
| 해제일 | `YYYY-MM-DD` 형식 |
| 물량 | 주식수 (쉼표 있어도 됨) |

- 다음 배치(자정 자동 또는 수동 실행) 때 운영_락업일정과 홈페이지에 편입됩니다.
- 같은 행을 계속 두면 매 배치마다 갱신되며 중복 생성되지 않습니다. 값이 틀리면 `검토필요` 탭에 사유가 남습니다.
- 행을 지우면 그 뒤로 갱신만 멈추고, 이미 편입된 이벤트는 남습니다.

## GitHub Repository Secrets

GitHub 저장소의 `Settings` → `Secrets and variables` → `Actions`에 아래 값을 저장합니다.

- `KRX_API_KEY`
- `DATA_GO_KR_API_KEY`
- `DART_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Google 서비스 계정 JSON 파일의 전체 내용
- `GOOGLE_SHEET_ID`: `1THcCbn5n9NQesOa0JHV3B-pdCeab8sRqMZhxOIWI-pg`

`.env`와 Google 서비스 계정 JSON은 GitHub에 커밋하지 않습니다.
