# IPO 락업 해제 캘린더 v6

신규상장 IPO 종목의 락업 해제 일정을 자동 집계해 웹사이트로 보여주는 프로젝트입니다.

핵심은 **DART 파싱값과 금융위 API 확인값을 분리**하고, Google Sheet의 `종목관리`와 `보정작업`을 단일 운영 창구로 사용하는 구조입니다. 기존 JSON/CSV는 자동 원장으로 유지되어 시트를 초기화해도 전체 DART 재파싱 없이 복구할 수 있습니다.

---

## 1. API Key 입력

프로젝트 루트에 `.env` 파일을 만들고 아래 값을 입력합니다.

```env
KRX_API_KEY=
DATA_GO_KR_API_KEY=
DART_API_KEY=
```

- `KRX_API_KEY`: KRX Open API
- `DATA_GO_KR_API_KEY`: 공공데이터포털 금융위원회_주식발행정보 API
- `DART_API_KEY`: DART OpenAPI. 투자설명서/증권신고서 원문 다운로드 및 유통가능 요약표 파싱에 사용

`.env.example`을 복사해 `.env`로 바꿔도 됩니다.

---

## 2. 실행

```powershell
python -m pip install -r requirements.txt
python -m scripts.build --year 2026
npm.cmd install
npm.cmd run dev -- -p 3002
```

브라우저 접속:

```text
http://localhost:3002
```

이미 신규 IPO universe를 만들어둔 뒤 빠르게 다시 돌릴 때:

```powershell
python -m scripts.build --year 2026 --no-refresh-universe
```

이미 편입된 종목도 DART를 다시 파싱하고 싶을 때:

```powershell
python -m scripts.build --year 2026 --no-refresh-universe --reparse-existing
```

---

## 3. 데이터 생성 구조

### A. 신규 종목 최초 편입

신규상장 IPO 종목으로 판단된 종목은 최초 편입 시 아래를 한 번 실행합니다.

```text
KRX 신규상장 후보 감지
→ IPO 여부 확인
→ DART OpenAPI로 최신 투자설명서/증권신고서 다운로드
→ “상장 후 유통가능 주식수 현황” 요약표만 파싱
→ 구주·보호예수 미래 해제 물량 생성
→ DART 증권발행실적보고서에서 IPO기관 의무보유확약 물량 생성
→ 금융위 API 반환정보 확인
→ data/lockup_admin.csv 및 data/site_data.json 생성
```

상세 주주별 표는 파싱하지 않습니다. 변수가 많아 정확도가 낮아질 수 있기 때문에, 아래 요약표만 사용합니다.

```text
구분 | 주식수 | 유통가능 주식수 비율
상장일 유통가능
상장 후 1개월 뒤 유통가능
상장 후 3개월 뒤 유통가능
상장 후 6개월 뒤 유통가능
상장 후 12개월 뒤 유통가능
상장 후 30개월 뒤 유통가능
```

각 행의 `누적 유통가능 주식수 - 직전행 누적 유통가능 주식수`를 구주·보호예수 해제 물량으로 계산합니다.

### B. 이미 편입된 종목

이미 `data/lockup_admin.csv`에 있는 종목은 기본적으로 DART를 다시 파싱하지 않습니다.

```text
이미 편입 완료된 종목
→ DART 재파싱 X
→ 금융위 API만 조회
→ 반환 여부/반환일/반환주식수 확인
→ 상태와 최종표시값만 업데이트
```

DART 재파싱이 필요하면 `--reparse-existing` 옵션을 사용합니다.

---

## 4. 운영 시트와 자동 원장

운영자는 Google Sheet의 아래 세 탭만 수정합니다.

- `종목관리`: IPO일정/락업 편입, 수동편입, 비공개, 제외고정
- `보정작업`: IPO일정 누락값과 락업 수기 보정
- `휴장일`: 거래소 휴장일

`IPO일정_현황`, `IPO기관_현황`, `기존주주_현황`, `정정이력`은 읽기 전용 결과입니다. 자세한 입력 방법과 첫 배치 이관 규칙은 [OPERATIONS.md](OPERATIONS.md)를 확인하세요.

자동 원장의 중심은 `data/lockup_admin.csv`이며, 배치가 관리 시트의 명령을 이 파일과 JSON에 반영합니다.

주요 컬럼:

| 컬럼 | 의미 |
|---|---|
| `planned_date`, `planned_qty` | DART 파싱 예정값 |
| `api_return_date`, `api_return_qty` | 금융위 API 반환 확인값 |
| `manual_date`, `manual_qty` | 운영자가 직접 수정한 값 |
| `manual_lock` | 수동값 고정 여부. `Y`면 수동값 우선, `N`이면 자동값 우선 |
| `final_date`, `final_qty` | 홈페이지에 실제 노출되는 값 |
| `status` | 예정, 반환확인, 반환확인_API수정, 수동확인, 수동/API불일치 등 |
| `review_needed` | 운영자 확인 필요 여부 |
| `memo` | 운영자 메모 |

---

## 5. 최종표시값 우선순위

```text
1순위: manual_lock=Y인 수동값
2순위: 금융위 API 반환값
3순위: DART 파싱값
```

### 케이스 1. 수동고정=N + API 값 있음

API 값이 최종표시값으로 자동 반영됩니다.

DART와 API 수량이 달라도 운영자가 따로 볼 필요는 없고, `lockup_log.csv`에만 이력이 남습니다.

```text
DART 117,647주
API 100,000주
→ 최종표시 100,000주
→ status=반환확인_API수정
→ review_needed=N
→ 로그 기록
```

### 케이스 2. 수동고정=Y + API 값과 수동값이 다름

운영자 수동값을 유지하고, 검토필요로 표시합니다.

```text
수동 117,647주
API 100,000주
→ 최종표시 117,647주 유지
→ status=수동/API불일치
→ review_needed=Y
```

운영자가 API가 맞다고 판단하면 `보정작업`에서 고정 보정을 취소하거나 자동값을 선택합니다. 그러면 다음 배치 때 최종표시값이 API 기준으로 자동 전환됩니다.

---

## 6. 검토/로그 파일

```text
data/review_needed.csv
```

진짜 사람이 봐야 하는 항목만 모읍니다.

- 수동고정값과 API값 불일치
- DART 유통가능 요약표 마지막 주식수와 KRX 상장주식수 불일치
- DART 투자설명서/증권신고서 표 파싱 실패

```text
data/lockup_log.csv
```

자동 변경 이력을 누적합니다. 운영자가 보통 직접 수정할 필요는 없습니다.

---

## 7. 홈페이지 표시

- 홈: 30일 이내 락업 해제 예정 정보. 같은 종목·같은 해제일이면 IPO기관 + 구주·보호예수 물량을 합산 표시
- 종목 상세: 합산 숫자 아래에 IPO기관 / 구주·보호예수 세부 물량 표시
- 전체 일정: `전체 / IPO기관 / 구주·보호예수` 필터 제공
- CSV 다운로드: 현재 선택된 필터 기준으로 다운로드

---

## 8. 주의사항

- `.env`는 절대 공유하거나 Git에 올리지 마세요.
- 시트 행 삭제는 종목 삭제나 작업 취소로 해석하지 않습니다. `제외고정` 또는 `처리상태=취소`를 사용하세요.
- 자동값 컬럼은 읽기 전용이며 `보정작업`의 수기값만 수정하세요.
- DART 표가 불안정하면 보정작업에 남고, 필요할 때 `임시` 또는 `고정`으로 보정합니다.


## v6.1 수정
- 투자설명서에 `5년` 등 장기 락업 기간이 나와도 배치가 중단되지 않도록 `N개월`/`N년` 일반 처리 로직을 추가했습니다.
- Mac에서 `npm: command not found`가 나오면 Node.js LTS 설치가 필요합니다.
