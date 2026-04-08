#!/bin/sh
# Title: Loki
# Requires: /root/payloads/user/reconnaissance/loki
# Category: Reconnaissance
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/reconnaissance/loki"
DATA_DIR="$PAYLOAD_DIR/data"

cd "$PAYLOAD_DIR" || exit 1

# Setup paths
export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"
export CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1

# NMAPDIR
if [ -d "$PAYLOAD_DIR/share/nmap/scripts" ]; then
    export NMAPDIR="$PAYLOAD_DIR/share/nmap"
elif [ -d "/mmc/usr/share/nmap/scripts" ]; then
    export NMAPDIR="/mmc/usr/share/nmap"
else
    export NMAPDIR="/usr/share/nmap"
fi

# Check python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 not found"
    exit 1
fi

# Stop pager service if running
/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

# Create data directory
mkdir -p "$DATA_DIR" 2>/dev/null

# Run Loki menu directly
while true; do
    cd "$PAYLOAD_DIR"
    python3 loki_menu.py
    EXIT_CODE=$?

    # Exit code 42 = hand off to another payload
    if [ "$EXIT_CODE" -eq 42 ] && [ -f "$DATA_DIR/.next_payload" ]; then
        NEXT_SCRIPT=$(cat "$DATA_DIR/.next_payload")
        rm -f "$DATA_DIR/.next_payload"
        if [ -f "$NEXT_SCRIPT" ]; then
            sh "$NEXT_SCRIPT"
            [ $? -eq 42 ] && continue
        fi
    fi

    # Exit code 99 = return to Loki main menu
    if [ "$EXIT_CODE" -eq 99 ]; then
        continue
    fi

    break
done

exit 0
