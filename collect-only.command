#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 collect.py --countries ALL --limit 16 --workers 8
result=$?
print "按 Enter 關閉視窗。"
read
exit "$result"
