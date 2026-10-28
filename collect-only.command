#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if (( $# )); then
  python3 collect.py "$@"
else
  source ./scan-mode.zsh || exit 0
  python3 collect.py --mode "$SCAN_MODE"
fi
result=$?
print "按 Enter 關閉視窗。"
read
exit "$result"
