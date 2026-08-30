# Value Chain Review Checklist

- Generated: 2026-08-23T11:04:48
- Companies: 56
- Domestic listed: 38
- KRX matched: 38
- DART matched: 0
- Missing role detail: 0

## 돌아오면 먼저 볼 것

1. 아래 `사용자 검토 필요` 항목부터 봅니다.
2. `API 연결 후 자동 검증`은 이 로컬 폴더에 `.env`가 없어서 남은 대기 항목입니다.
3. 비상장·해외 기업은 Toss/DeepSearch, IR, 수기 중 어떤 기준으로 관리할지 정해야 합니다.

## 사용자 검토 필요

- [ ] SK실트론 (실리콘 웨이퍼): 국내 비상장사: 재무/시총 별도 수기 또는 DeepSearch/Toss 소스 필요
- [ ] SK스페셜티 (특수가스): 국내 비상장사: 재무/시총 별도 수기 또는 DeepSearch/Toss 소스 필요
- [ ] 세메스 (전공정 장비): 국내 비상장사: 재무/시총 별도 수기 또는 DeepSearch/Toss 소스 필요
- [ ] ASML (EUV 노광 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Tokyo Electron (산화·증착·세정 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Lam Research (식각 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Applied Materials (증착·식각 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Axcelis (이온주입 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] TSMC (첨단 파운드리): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] KLA (검사·계측): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Air Liquide (산업가스): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] JSR (포토레지스트): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Shin-Etsu (실리콘 웨이퍼·소재): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] SUMCO (실리콘 웨이퍼): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] DISCO (다이싱·그라인더 장비): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] Ibiden (FC-BGA 기판): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] DuPont (CMP·전자소재): 해외 기업: 별도 해외 IR/API 기준 필요
- [ ] onsemi (전력반도체): 해외 기업: 별도 해외 IR/API 기준 필요

## API 연결 후 자동 검증

- 국내 상장사 API 검증 대기: 38개
- 이 항목들은 종목코드와 역할 설명은 채워져 있고, `.env`의 KRX/DART/Toss/DeepSearch 키 연결 후 시총·가격·재무값을 치환하면 됩니다.

## 산출물

- `data/value-chain/audit.csv`: 기업별 검토 테이블
- `data/value-chain/audit.json`: 자동화용 원본
- `lib/valueChain.ts`: 현재 데모 데이터와 역할 설명

## Notes

- KRX/DART API keys are not available in this local run, so live verification is marked as pending.
- Demo financial values must not be treated as production data.
- For Toss/DeepSearch, add env keys and map them into this audit pipeline before launch.
