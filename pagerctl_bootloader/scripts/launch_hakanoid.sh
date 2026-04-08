#!/bin/sh
# Title: Hakanoid
# Requires: /root/payloads/user/games/hakanoid
# Category: Games
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/games/hakanoid"

cd "$PAYLOAD_DIR" || exit 1

export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

chmod +x ./hakanoid 2>/dev/null
./hakanoid

exit 0
