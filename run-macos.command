#!/bin/zsh
cd -- "${0:A:h}" || exit 1

pause_and_exit() {
  local code="$1"
  print ""
  print "完成或遇到錯誤。按 Enter 關閉此視窗。"
  read
  exit "$code"
}

for tool in python3 curl node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    print "找不到必要指令：$tool。請先安裝 Python 3.11+、curl 與 Node.js。"
    pause_and_exit 1
  fi
done

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  print "需要 Python 3.11 或更新版本。"
  pause_and_exit 1
fi

if [[ ! -x node_modules/wrangler/bin/wrangler.js ]]; then
  print "首次執行：安裝鎖定版本的 Wrangler…"
  npm ci --ignore-scripts || pause_and_exit 1
fi

if [[ ! -f deploy/project.env ]]; then
  cp deploy/project.env.example deploy/project.env || pause_and_exit 1
  print "已建立 deploy/project.env。請填入你自己的 Cloudflare Pages 專案名稱後，再雙擊一次。"
  open -a TextEdit deploy/project.env
  pause_and_exit 0
fi

PROJECT_NAME=$(sed -n 's/^PAGES_PROJECT_NAME=//p' deploy/project.env | tail -n 1 | tr -d '\r')
if [[ -z "$PROJECT_NAME" || "$PROJECT_NAME" == "replace-with-your-pages-project" ]]; then
  print "請先在 deploy/project.env 設定 PAGES_PROJECT_NAME。"
  open -a TextEdit deploy/project.env
  pause_and_exit 1
fi

export PAGES_PROJECT_NAME="$PROJECT_NAME"
export PAGES_BRANCH=$(sed -n 's/^PAGES_BRANCH=//p' deploy/project.env | tail -n 1 | tr -d '\r')
PAGES_BRANCH=${PAGES_BRANCH:-main}
python3 publish.py
pause_and_exit "$?"
