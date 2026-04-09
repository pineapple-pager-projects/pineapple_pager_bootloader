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

# Check and install missing Python modules
MISSING=""
python3 -c "import sqlite3" 2>/dev/null || MISSING="$MISSING python3-sqlite3"
python3 -c "import ctypes" 2>/dev/null || MISSING="$MISSING python3-ctypes"

if [ -n "$MISSING" ]; then
    echo "Installing missing packages:$MISSING"
    opkg update 2>/dev/null
    for pkg in $MISSING; do
        opkg -d mmc install $pkg 2>/dev/null
    done
fi

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

mkdir -p /mmc/root/loot/wardrive/captures
mkdir -p /mmc/root/loot/wardrive/exports

python3 wardrive.py

exit 0
