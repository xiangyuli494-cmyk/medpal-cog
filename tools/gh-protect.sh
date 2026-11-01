#!/usr/bin/env bash
# 幂等地给 medpal-cog 的 main 装分支保护（需要 admin 权限的 GitHub token）。
# 用法：
#   bash tools/gh-protect.sh            # 直接装
#   DRY_RUN=1 bash tools/gh-protect.sh  # 只打印将要提交的 JSON
#   REPO=owner/name BRANCH=main bash tools/gh-protect.sh
# token 来源：$GITHUB_TOKEN，或从本机 git credential 里取（GCM 已登录时可用）。
set -euo pipefail

REPO=${REPO:-xiangyuli494-cmyk/medpal-cog}
BRANCH=${BRANCH:-main}
# ENFORCE_ADMINS=1 → 连 admin/owner 也必须走 PR + approve（没人能直推、没人能绕过）。
# 现在只有 T1 一个 collaborator，开了就没人能批 T1 的 PR；等 T2/T3 账号加进来当天再开：
#   ENFORCE_ADMINS=1 bash tools/gh-protect.sh
ENFORCE_ADMINS=${ENFORCE_ADMINS:-0}
if [ "${ENFORCE_ADMINS}" = "1" ]; then ENFORCE_JSON=true; else ENFORCE_JSON=false; fi

# 必需检查项的名字 = ci.yml 里各 job 的 name（不是 job id）。
# 名字对不上时，PR 会一直卡在 "Expected — Waiting for status to be reported"。
if [ -z "${CHECKS:-}" ]; then
  CI=.github/workflows/ci.yml
  if [ -f "$CI" ]; then
    CHECKS=$(sed -n 's/^    name: //p' "$CI" | paste -sd, -)
  else
    CHECKS="lint (ruff),test (pytest),pipeline (skeleton + eval)"
  fi
fi
echo "必需检查：$CHECKS"

api() { curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$@"; }

if [ -z "${GITHUB_TOKEN:-}" ]; then
  TOKEN=$(printf "protocol=https\nhost=github.com\n\n" | GIT_TERMINAL_PROMPT=0 git credential fill 2>/dev/null | sed -n "s/^password=//p")
  if [ -z "${TOKEN:-}" ]; then
    echo "没有 token：先 export GITHUB_TOKEN=<有 admin 权限的 PAT>" >&2
    exit 1
  fi
else
  TOKEN=$GITHUB_TOKEN
fi

json=$(printf '{"required_status_checks":{"strict":false,"contexts":[%s]},"enforce_admins":%s,"required_pull_request_reviews":{"dismiss_stale_reviews":true,"require_code_owner_reviews":false,"required_approving_review_count":1,"require_last_push_approval":false},"restrictions":null,"required_conversation_resolution":true,"allow_force_pushes":false,"allow_deletions":false,"required_linear_history":false}' \
  "$(echo "$CHECKS" | sed 's/[^,]*/"&"/g')" "$ENFORCE_JSON")

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "$json"
  exit 0
fi

code=$(api -o /tmp/protect.json -w "%{http_code}" -X PUT \
  "https://api.github.com/repos/$REPO/branches/$BRANCH/protection" \
  -d "$json")

if [ "$code" = "200" ]; then
  echo "OK  $REPO@$BRANCH 已保护：>=1 approve + CI($CHECKS) + 禁强推/禁删"
  api "https://api.github.com/repos/$REPO/branches/$BRANCH/protection" \
    | grep -E '"(required_approving_review_count|enforce_admins|dismiss_stale_reviews|enabled)"' | head -8
else
  echo "FAIL HTTP $code" >&2
  cat /tmp/protect.json >&2
  exit 2
fi