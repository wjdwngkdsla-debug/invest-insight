# 운영 방법

## 자동 갱신

- GitHub Actions가 매일 한국시간 00:00에 실행됩니다.
- Google Sheet의 수동 수정값을 먼저 내려받습니다.
- KRX, DART, 공공데이터 API를 실행합니다.
- `data/site_data.json`과 운영 CSV를 갱신합니다.
- Google Sheet를 다시 갱신하고 변경된 데이터는 GitHub에 자동 커밋합니다.
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

## GitHub Repository Secrets

GitHub 저장소의 `Settings` → `Secrets and variables` → `Actions`에 아래 값을 저장합니다.

- `KRX_API_KEY`
- `DATA_GO_KR_API_KEY`
- `DART_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Google 서비스 계정 JSON 파일의 전체 내용
- `GOOGLE_SHEET_ID`: `1THcCbn5n9NQesOa0JHV3B-pdCeab8sRqMZhxOIWI-pg`

`.env`와 Google 서비스 계정 JSON은 GitHub에 커밋하지 않습니다.
