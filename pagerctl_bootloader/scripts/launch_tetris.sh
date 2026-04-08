#!/bin/sh
# Title: Tetris
# Requires: /root/payloads/user/games/tetris
# Category: Games
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/games/tetris"

cd "$PAYLOAD_DIR" || exit 1

export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

chmod +x ./tetris_launcher ./tetris_portrait_l ./tetris_portrait_r ./tetris_landscape 2>/dev/null
./tetris_launcher

exit 0
