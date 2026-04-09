#!/bin/sh
# Title: Wardrive
# Requires: /root/payloads/user/reconnaissance/wardrive
# Category: Reconnaissance
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/reconnaissance/wardrive"

cd "$PAYLOAD_DIR" || exit 1

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

mkdir -p /mmc/root/loot/wardrive/captures
mkdir -p /mmc/root/loot/wardrive/exports

python3 wardrive.py

exit 0
