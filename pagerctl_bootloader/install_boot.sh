#!/bin/sh
# Install/uninstall the Pagerctl Bootloader as the boot default
# Usage: ./install_boot.sh enable   — boot into bootloader instead of Pager UI
#        ./install_boot.sh disable  — restore normal Pager UI boot

LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_SCRIPT="/etc/init.d/pagerctl_bootloader"

case "$1" in
    enable)
        cat > "$INIT_SCRIPT" << 'INITEOF'
#!/bin/sh /etc/rc.common
# Pagerctl Bootloader — runs before pineapplepager service
USE_PROCD=1
START=49

start_service() {
    # Stop pineapplepager if it's trying to start
    /etc/init.d/pineapplepager disable 2>/dev/null
    /etc/init.d/pineapplepager stop 2>/dev/null

    LAUNCHER_DIR="/root/payloads/user/general/pagerctl_bootloader"
    if [ ! -f "$LAUNCHER_DIR/launch_menu.py" ]; then
        # Bootloader not found, re-enable pager service
        /etc/init.d/pineapplepager enable 2>/dev/null
        /etc/init.d/pineapplepager start 2>/dev/null
        return
    fi

    # Run the bootloader (blocks until user selects Exit to Pager UI)
    export PATH="/mmc/usr/bin:$LAUNCHER_DIR/bin:$PATH"
    export PYTHONPATH="$LAUNCHER_DIR/lib:$LAUNCHER_DIR:$PYTHONPATH"
    export LD_LIBRARY_PATH="/mmc/usr/lib:$LAUNCHER_DIR/lib:$LD_LIBRARY_PATH"

    cd "$LAUNCHER_DIR"
    python3 launch_menu.py &
}

stop_service() {
    killall -9 python3 2>/dev/null
}
INITEOF
        chmod +x "$INIT_SCRIPT"
        # Enable bootloader, disable pager service
        "$INIT_SCRIPT" enable
        /etc/init.d/pineapplepager disable 2>/dev/null
        echo "Pagerctl Bootloader enabled as boot default."
        echo "The pager will boot into the launcher menu."
        echo "Select 'Exit to Pager UI' to start the normal pager interface."
        echo ""
        echo "To restore normal boot: ./install_boot.sh disable"
        ;;

    disable)
        if [ -f "$INIT_SCRIPT" ]; then
            "$INIT_SCRIPT" disable 2>/dev/null
            rm -f "$INIT_SCRIPT"
        fi
        # Re-enable pager service
        /etc/init.d/pineapplepager enable 2>/dev/null
        echo "Normal Pager UI boot restored."
        ;;

    status)
        if [ -f "$INIT_SCRIPT" ]; then
            echo "Pagerctl Bootloader is ENABLED as boot default."
        else
            echo "Normal Pager UI boot (bootloader not enabled)."
        fi
        ;;

    *)
        echo "Usage: $0 {enable|disable|status}"
        exit 1
        ;;
esac
