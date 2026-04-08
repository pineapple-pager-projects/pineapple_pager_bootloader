#!/bin/sh
# Title: Chasing Your Tail
# Requires: /mmc/root/payloads/user/reconnaissance/cyt
# Category: Reconnaissance
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/mmc/root/payloads/user/reconnaissance/cyt"
DB="$PAYLOAD_DIR/cyt.db"
PYTHON=""

cd "$PAYLOAD_DIR" || exit 1

# Setup paths
export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

PYTHON=$(command -v python3)
if [ -z "$PYTHON" ]; then
    echo "Python3 not found"
    exit 1
fi

# Stop pager service
/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

# GPS setup
uci set gpsd.core.device='/dev/ttyACM0' 2>/dev/null
uci commit gpsd 2>/dev/null
/etc/init.d/gpsd restart 2>/dev/null || \
    /usr/sbin/gpsd -n -b /dev/ttyACM0 2>/dev/null &

# Launch CYT GUI directly
while true; do
    "$PYTHON" "$PAYLOAD_DIR/cyt_app.py" --db "$DB" --limit 20
    EXIT_CODE=$?
    [ "$EXIT_CODE" -eq 99 ] && continue
    # Stop daemons on exit
    for pidfile in "$PAYLOAD_DIR/ble.pid" "$PAYLOAD_DIR/analyzer.pid" \
                   "$PAYLOAD_DIR/wifi.pid" "$PAYLOAD_DIR/web.pid"; do
        [ -f "$pidfile" ] || continue
        pid=$(cat "$pidfile" 2>/dev/null)
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
        rm -f "$pidfile"
    done
    break
done

exit 0
