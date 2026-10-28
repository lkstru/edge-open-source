# Shared Finder menu. Sourcing this file sets SCAN_MODE.
SCAN_MODE=daily
if [[ -t 0 ]]; then
  print "1. 日常更新：每國最多 16 個新候選"
  print "2. 深度掃描：每國最多 64 個新候選，找到 4 個初測可用節點即停止"
  print "兩種模式都會複查舊節點，並在發布前再次驗證。深度掃描可能需要較長時間。"
  read 'scan_choice?請選擇 [1 / 2，Enter 預設 1，q 取消]：'
  case "$scan_choice" in
    1|"") SCAN_MODE=daily ;;
    2) SCAN_MODE=deep ;;
    q|Q) print "已取消。"; return 1 ;;
    *) print "選項無效，未開始掃描。"; return 1 ;;
  esac
fi
