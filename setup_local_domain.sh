#!/bin/bash
# Script cấu hình tên miền nội bộ http://lms.bachanhtu/sinhhoc12 trên macOS
# Cách dùng:
#   sudo bash setup_local_domain.sh
# Sau đó chạy máy chủ:
#   sudo PORT=80 python3 server.py
# (Hoặc không cần sudo ở bước chạy server nếu dùng http://lms.bachanhtu:8080/sinhhoc12)

set -e

HOST_ENTRY="127.0.0.1 lms.bachanhtu"
HOSTS_FILE="/etc/hosts"

if grep -q "lms.bachanhtu" "$HOSTS_FILE"; then
  echo "✓ Đã có cấu hình lms.bachanhtu trong $HOSTS_FILE"
else
  echo "$HOST_ENTRY" >> "$HOSTS_FILE"
  echo "✓ Đã thêm '$HOST_ENTRY' vào $HOSTS_FILE"
fi

# Làm mới bộ nhớ đệm DNS của macOS
dscacheutil -flushcache 2>/dev/null || true
killall -HUP mDNSResponder 2>/dev/null || true

echo ""
echo "Hoàn tất cấu hình tên miền nội bộ!"
echo "- Chạy không cần cổng 8080:  sudo PORT=80 python3 server.py  ->  http://lms.bachanhtu/sinhhoc12"
echo "- Hoặc chạy bình thường:     python3 server.py              ->  http://lms.bachanhtu:8080/sinhhoc12"
