#!/bin/zsh
set -e

ROOT="${0:A:h}"
cd "$ROOT"

echo "토스 수정주가 주간 확인을 시작합니다."
echo "GitHub Desktop에서 Pull origin을 먼저 완료한 상태여야 합니다."
/usr/bin/python3 -m scripts.toss_ipo_adjustment

echo ""
echo "완료됐습니다. 다음 GitHub 일일 배치부터 홈페이지 수익률에 반영됩니다."
echo "창을 닫으려면 Enter를 누르세요."
read
