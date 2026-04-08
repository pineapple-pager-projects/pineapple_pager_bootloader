#!/bin/sh
# Title: Pagerctl Bootloader
# Description: Boot launcher menu - run payloads without the Pineapple Pager UI
# Author: brAinphreAk
# Version: 1.0
# Category: Utilities
# Library: libpagerctl.so (pagerctl)

_PAYLOAD_TITLE="Pagerctl Bootloader"
_PAYLOAD_AUTHOR_NAME="brAinphreAk"
_PAYLOAD_VERSION="1.0"
_PAYLOAD_DESCRIPTION="Boot menu - launch payloads without the Pineapple Pager UI"

PAYLOAD_DIR="/root/payloads/user/general/pagerctl_bootloader"

# Setup paths (python3 lives in /mmc/usr/bin on the pager)
export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

if [ ! -f "$PAYLOAD_DIR/lib/libpagerctl.so" ]; then
    LOG "red" "libpagerctl.so not found in $PAYLOAD_DIR/lib/"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    LOG "red" "Python3 not found. Install with: opkg -d mmc install python3 python3-ctypes"
    exit 1
fi

# Kill boot animation and stop pager service (we're taking over the display)
killall boot_animation 2>/dev/null
/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

# Run the launcher menu
cd "$PAYLOAD_DIR"
python3 launch_menu.py
