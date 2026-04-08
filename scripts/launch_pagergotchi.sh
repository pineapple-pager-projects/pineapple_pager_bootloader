#!/bin/sh
# Title: PagerGotchi
# Requires: /root/payloads/user/reconnaissance/pagergotchi
# Category: Reconnaissance
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/reconnaissance/pagergotchi"

cd "$PAYLOAD_DIR" || exit 1

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

python3 run_pagergotchi.py

exit 0
