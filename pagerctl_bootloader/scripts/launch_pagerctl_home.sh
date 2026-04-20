#!/bin/sh
# Title: Pagerctl Home
# Requires: /root/payloads/user/general/pagerctl_home
# Category: General
# Direct launcher — custom home screen with theme engine

PAYLOAD_DIR="/root/payloads/user/general/pagerctl_home"

cd "$PAYLOAD_DIR" || exit 1

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

python3 pagerctl_home.py

exit 0
