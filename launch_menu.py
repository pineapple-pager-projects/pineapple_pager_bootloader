#!/usr/bin/env python3
"""
Pagerctl Bootloader — Boot launcher menu for WiFi Pineapple Pager.
Uses pagerctl for LCD rendering with its own theme config.

Can be run two ways:
1. As a normal payload from the Pineapple Pager UI
2. On boot before the pager service starts

Customize via launcher_config.json:
{
    "title": "My Launcher",
    "bg_image": "images/bg.png",
    "font": "fonts/menu.ttf",
    "title_font_size": 28,
    "item_font_size": 22,
    "colors": {
        "title": [255, 255, 255],
        "selected": [100, 200, 255],
        "unselected": [160, 160, 160],
        "highlight_bg": [30, 50, 80]
    },
    "payloads": [
        {"name": "Loki", "path": "/root/payloads/user/reconnaissance/loki/payload.sh"},
        {"name": "Pagergotchi", "path": "/root/payloads/user/utilities/pagergotchi/payload.sh"}
    ]
}

All paths in the config are relative to the launcher directory unless absolute.
"""

import json
import os
import sys
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from pagerctl import Pager

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TITLE = "Pagerctl Bootloader"

# Font search order
FONT_SEARCH = [
    os.path.join(SCRIPT_DIR, "fonts", "menu.ttf"),
    os.path.join(SCRIPT_DIR, "fonts", "menu.TTF"),
    "/pineapple/ui/Steelfish.ttf",
    "/root/payloads/user/reconnaissance/loki/resources/fonts/Arial.ttf",
]

DEFAULT_COLORS = {
    'title': [255, 255, 255],
    'selected': [100, 200, 255],
    'unselected': [160, 160, 160],
    'highlight_bg': [30, 50, 80],
}

PAGER_UI_ENTRY = {"name": "Exit to Pager UI", "path": "__pager_service__"}
SETTINGS_ENTRY = {"name": "Settings", "path": "__settings__"}
SHUTDOWN_ENTRY = {"name": "Shutdown", "path": "__shutdown__"}

INIT_SCRIPT_PATH = "/etc/init.d/pagerctl_bootloader"


def get_active_theme_bg():
    """Get the background image from the active pager theme."""
    try:
        result = subprocess.run(
            ['uci', 'get', 'system.@pager[0].theme_path'],
            capture_output=True, text=True, timeout=5
        )
        theme_path = result.stdout.strip()
        if theme_path:
            bg = os.path.join(theme_path, 'assets', 'alert_dialog_bg_term_blue.png')
            if os.path.isfile(bg):
                return bg
    except Exception:
        pass
    # Fallback: check known theme locations
    for base in ('/root/themes', '/lib/pager/themes'):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            bg = os.path.join(base, name, 'assets', 'alert_dialog_bg_term_blue.png')
            if os.path.isfile(bg):
                return bg
    return None

SCREEN_W = 480
SCREEN_H = 222


def find_font():
    """Find the best available font."""
    for path in FONT_SEARCH:
        if os.path.isfile(path):
            return path
    return None


def resolve_path(path):
    """Resolve a path — relative paths are relative to SCRIPT_DIR."""
    if os.path.isabs(path):
        return path
    return os.path.join(SCRIPT_DIR, path)


# ---------------------------------------------------------------------------
# Payload discovery
# ---------------------------------------------------------------------------
def discover_payloads():
    """Scan scripts/ directory for launch scripts.
    Each script must have:
        # Title: Display Name
        # Requires: /path/to/payload/directory
        # Category: Category Name (optional, defaults to "Other")
    Only shows payloads where the Requires directory exists (payload is installed)."""
    payloads = []
    scripts_dir = os.path.join(SCRIPT_DIR, 'scripts')
    if not os.path.isdir(scripts_dir):
        return payloads

    for filename in sorted(os.listdir(scripts_dir)):
        if not filename.startswith('launch_') or not filename.endswith('.sh'):
            continue
        script_path = os.path.join(scripts_dir, filename)
        if not os.path.isfile(script_path):
            continue

        title = None
        requires = None
        category = "Other"
        try:
            with open(script_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('# Title:'):
                        title = line[len('# Title:'):].strip()
                    elif line.startswith('# Requires:'):
                        requires = line[len('# Requires:'):].strip()
                    elif line.startswith('# Category:'):
                        category = line[len('# Category:'):].strip()
                    if title and requires:
                        break
        except Exception:
            continue

        if not title:
            continue

        # Only add if the required payload directory exists
        if requires and not os.path.isdir(requires):
            continue

        payloads.append({'name': title, 'path': script_path, 'category': category})

    return payloads


def group_by_category(payloads):
    """Group payloads by category. Returns ordered dict of category -> [payloads]."""
    categories = {}
    for p in payloads:
        cat = p['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p)
    return categories


# ---------------------------------------------------------------------------
# Launcher UI
# ---------------------------------------------------------------------------
class LauncherMenu:
    def __init__(self):
        self.pager = Pager()
        self.pager.init()
        self.pager.set_rotation(270)

        # Load config
        config_path = os.path.join(SCRIPT_DIR, 'launcher_config.json')
        self.config = {}
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
            except Exception:
                pass

        # Colors — config overrides defaults
        config_colors = self.config.get('colors', {})
        self.colors = {
            'title': config_colors.get('title', DEFAULT_COLORS['title']),
            'selected': config_colors.get('selected', DEFAULT_COLORS['selected']),
            'unselected': config_colors.get('unselected', DEFAULT_COLORS['unselected']),
            'highlight_bg': config_colors.get('highlight_bg', DEFAULT_COLORS['highlight_bg']),
        }

        # Background image — config override, or active pager theme default
        bg = self.config.get('bg_image')
        if bg:
            self.bg_image = resolve_path(bg)
        else:
            self.bg_image = get_active_theme_bg()

        # Fonts
        font_cfg = self.config.get('font')
        if font_cfg:
            self.font = resolve_path(font_cfg)
        else:
            self.font = find_font()

        # Title font (separate from menu font)
        title_font_cfg = self.config.get('title_font')
        if title_font_cfg:
            self.title_font = resolve_path(title_font_cfg)
        else:
            self.title_font = self.font

        # Title
        self.title = self.config.get('title', DEFAULT_TITLE)
        self.show_title = self.config.get('show_title', True)
        self.title_fs = self.config.get('title_font_size', 28)
        self.item_fs = self.config.get('item_font_size', 18)

        # Build payload list
        if 'payloads' in self.config:
            self.payloads = list(self.config['payloads'])
        else:
            self.payloads = discover_payloads()

        # Add settings, exit, and shutdown as last options
        self.payloads.append(SETTINGS_ENTRY)
        self.payloads.append(PAGER_UI_ENTRY)
        self.payloads.append(SHUTDOWN_ENTRY)

        self.selected = 0
        self.scroll_offset = 0
        self.sound_enabled = True
        self.category_view = False
        self.max_visible = 7

    def _rgb(self, color):
        return self.pager.rgb(color[0], color[1], color[2])

    def draw(self):
        """Draw the launcher menu."""
        # Background
        if self.bg_image and os.path.isfile(self.bg_image):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        if not self.font:
            self.pager.flip()
            return

        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])
        highlight_bg = self._rgb(self.colors['highlight_bg'])

        # Title — centered, using title font (can be hidden if baked into bg)
        if self.show_title:
            tw = self.pager.ttf_width(self.title, self.title_font, self.title_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, self.title, title_color, self.title_font, self.title_fs)

        # Menu items — centered, no highlight bar, matching Loki menu style
        item_height = 22
        start_y = 75
        visible_items = min(self.max_visible, len(self.payloads))

        # Keep selected item in view
        if self.selected < self.scroll_offset:
            self.scroll_offset = self.selected
        elif self.selected >= self.scroll_offset + visible_items:
            self.scroll_offset = self.selected - visible_items + 1

        for i in range(visible_items):
            idx = self.scroll_offset + i
            if idx >= len(self.payloads):
                break

            payload = self.payloads[idx]
            y = start_y + i * item_height
            is_selected = idx == self.selected

            color = selected_color if is_selected else unselected_color
            # Center text on screen
            tw = self.pager.ttf_width(payload['name'], self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, payload['name'], color, self.font, self.item_fs)

        # Scroll indicators
        if self.scroll_offset > 0:
            self.pager.draw_ttf(SCREEN_W - 30, start_y - 15, "^", unselected_color, self.font, 14)
        if self.scroll_offset + visible_items < len(self.payloads):
            self.pager.draw_ttf(SCREEN_W - 30, start_y + visible_items * item_height,
                                "v", unselected_color, self.font, 14)

        self.pager.flip()

    def _beep(self):
        """Play a short navigation beep if sound is enabled."""
        if self.sound_enabled:
            try:
                self.pager.beep(800, 30)
            except Exception:
                pass

    def _beep_select(self):
        """Play a selection confirmation beep if sound is enabled."""
        if self.sound_enabled:
            try:
                self.pager.beep(1200, 50)
            except Exception:
                pass

    def _show_category_menu(self, category_name, payloads):
        """Show payloads within a category. Returns selected payload or None for back."""
        selected = 0
        items = list(payloads) + [{"name": "Back", "path": "__back__"}]

        while True:
            self._draw_submenu(category_name, [p['name'] for p in items], selected)

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                selected = (selected - 1) % len(items)
                self._beep()
            elif button & self.pager.BTN_DOWN:
                selected = (selected + 1) % len(items)
                self._beep()
            elif button & self.pager.BTN_A:
                self._beep_select()
                if items[selected]['path'] == '__back__':
                    return None
                return items[selected]
            elif button & self.pager.BTN_B:
                self._beep()
                return None

    def run(self):
        """Main menu loop. Returns selected payload dict."""
        if self.category_view:
            return self._run_category_view()
        self.draw()
        while True:
            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                self.selected = (self.selected - 1) % len(self.payloads)
                self._beep()
                self.draw()
            elif button & self.pager.BTN_DOWN:
                self.selected = (self.selected + 1) % len(self.payloads)
                self._beep()
                self.draw()
            elif button & self.pager.BTN_A:
                self._beep_select()
                return self.payloads[self.selected]

    def _run_category_view(self):
        """Run with category navigation."""
        categories = group_by_category(
            [p for p in self.payloads if p.get('path') not in
             ('__pager_service__', '__settings__', '__shutdown__')]
        )
        cat_names = sorted(categories.keys())
        # Build menu: categories + system items
        menu_items = [{"name": cat, "path": "__category__"} for cat in cat_names]
        menu_items.append(SETTINGS_ENTRY)
        menu_items.append(PAGER_UI_ENTRY)
        menu_items.append(SHUTDOWN_ENTRY)

        selected = 0
        scroll_offset = 0

        while True:
            # Draw category menu
            if self.bg_image and os.path.isfile(self.bg_image):
                try:
                    self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
                except Exception:
                    self.pager.clear(self.pager.BLACK)
            else:
                self.pager.clear(self.pager.BLACK)

            if self.font:
                title_color = self._rgb(self.colors['title'])
                selected_color = self._rgb(self.colors['selected'])
                unselected_color = self._rgb(self.colors['unselected'])

                if self.show_title:
                    tw = self.pager.ttf_width(self.title, self.title_font, self.title_fs)
                    self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, self.title, title_color, self.title_font, self.title_fs)

                item_height = 22
                start_y = 75
                visible = min(self.max_visible, len(menu_items))

                if selected < scroll_offset:
                    scroll_offset = selected
                elif selected >= scroll_offset + visible:
                    scroll_offset = selected - visible + 1

                for i in range(visible):
                    idx = scroll_offset + i
                    if idx >= len(menu_items):
                        break
                    item = menu_items[idx]
                    y = start_y + i * item_height
                    is_sel = idx == selected
                    color = selected_color if is_sel else unselected_color
                    # Add arrow indicator for categories
                    label = item['name'] + " >" if item['path'] == '__category__' else item['name']
                    tw = self.pager.ttf_width(label, self.font, self.item_fs)
                    self.pager.draw_ttf((SCREEN_W - tw) // 2, y, label, color, self.font, self.item_fs)

                if scroll_offset > 0:
                    self.pager.draw_ttf(SCREEN_W - 30, start_y - 15, "^", unselected_color, self.font, 14)
                if scroll_offset + visible < len(menu_items):
                    self.pager.draw_ttf(SCREEN_W - 30, start_y + visible * item_height, "v", unselected_color, self.font, 14)

            self.pager.flip()

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                selected = (selected - 1) % len(menu_items)
                self._beep()
            elif button & self.pager.BTN_DOWN:
                selected = (selected + 1) % len(menu_items)
                self._beep()
            elif button & self.pager.BTN_A:
                self._beep_select()
                item = menu_items[selected]
                if item['path'] == '__category__':
                    # Enter category submenu
                    result = self._show_category_menu(item['name'], categories[item['name']])
                    if result:
                        return result
                else:
                    return item

    def _is_boot_enabled(self):
        """Check if bootloader is set to run on boot."""
        return os.path.exists("/etc/rc.d/S49pagerctl_bootloader")

    def _draw_submenu(self, title, items, selected):
        """Draw a submenu screen matching the main menu style."""
        if self.bg_image and os.path.isfile(self.bg_image):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])

        # Title
        tw = self.pager.ttf_width(title, self.title_font, self.title_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, title, title_color, self.title_font, self.title_fs)

        # Items
        start_y = 75
        for i, item in enumerate(items):
            y = start_y + i * 22
            color = selected_color if i == selected else unselected_color
            tw = self.pager.ttf_width(item, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item, color, self.font, self.item_fs)

        self.pager.flip()

    def _show_message(self, text, duration=1.5):
        """Show a brief centered message."""
        if self.bg_image and os.path.isfile(self.bg_image):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        color = self._rgb(self.colors['selected'])
        tw = self.pager.ttf_width(text, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 100, text, color, self.font, self.item_fs)
        self.pager.flip()
        time.sleep(duration)

    def _install_boot(self):
        """Install the bootloader as boot default."""
        init_script = '''#!/bin/sh /etc/rc.common
# Pagerctl Bootloader — runs before pineapplepager service
USE_PROCD=1
START=49

start_service() {
    # Kill boot animation so we can take over the display
    killall boot_animation 2>/dev/null

    /etc/init.d/pineapplepager disable 2>/dev/null
    /etc/init.d/pineapplepager stop 2>/dev/null

    LAUNCHER_DIR="/root/payloads/user/general/pagerctl_bootloader"
    if [ ! -f "$LAUNCHER_DIR/launch_menu.py" ]; then
        /etc/init.d/pineapplepager enable 2>/dev/null
        /etc/init.d/pineapplepager start 2>/dev/null
        return
    fi

    export PATH="/mmc/usr/bin:$LAUNCHER_DIR/bin:$PATH"
    export PYTHONPATH="$LAUNCHER_DIR/lib:$LAUNCHER_DIR:$PYTHONPATH"
    export LD_LIBRARY_PATH="/mmc/usr/lib:$LAUNCHER_DIR/lib:$LD_LIBRARY_PATH"

    cd "$LAUNCHER_DIR"
    python3 launch_menu.py &
}

stop_service() {
    return 0
}
'''
        try:
            with open(INIT_SCRIPT_PATH, 'w') as f:
                f.write(init_script)
            os.chmod(INIT_SCRIPT_PATH, 0o755)
            # Create symlink directly (don't call enable — it hangs via procd)
            symlink = "/etc/rc.d/S49pagerctl_bootloader"
            if os.path.exists(symlink):
                os.remove(symlink)
            os.symlink("../init.d/pagerctl_bootloader", symlink)
            # Disable pager service by removing its symlink
            pager_symlink = "/etc/rc.d/S50pineapplepager"
            if os.path.exists(pager_symlink):
                os.remove(pager_symlink)
            return True
        except Exception:
            return False

    def _uninstall_boot(self):
        """Remove the bootloader from boot and restore pager service."""
        try:
            # Remove bootloader symlink and init script
            symlink = "/etc/rc.d/S49pagerctl_bootloader"
            if os.path.exists(symlink):
                os.remove(symlink)
            if os.path.isfile(INIT_SCRIPT_PATH):
                os.remove(INIT_SCRIPT_PATH)
            # Re-enable pager service by creating its symlink
            pager_symlink = "/etc/rc.d/S50pineapplepager"
            if not os.path.exists(pager_symlink):
                os.symlink("../init.d/pineapplepager", pager_symlink)
            return True
        except Exception:
            return False

    def _draw_settings(self, selected, brightness, boot_enabled):
        """Draw the settings screen with brightness bar."""
        if self.bg_image and os.path.isfile(self.bg_image):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])

        # Title
        if self.show_title:
            tw = self.pager.ttf_width("Settings", self.title_font, self.title_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, "Settings", title_color, self.title_font, self.title_fs)

        # Brightness bar (item 0)
        bar_y = 75
        bar_x = 100
        bar_w = 280
        bar_h = 14

        bright_color = selected_color if selected == 0 else unselected_color
        label = f"Brightness: {brightness}%"
        tw = self.pager.ttf_width(label, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, bar_y - 20, label, bright_color, self.font, self.item_fs)

        if selected == 0:
            self.pager.rect(bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4, selected_color)
        self.pager.fill_rect(bar_x, bar_y, bar_w, bar_h, self._rgb([40, 40, 40]))
        fill_w = int(bar_w * brightness / 100)
        self.pager.fill_rect(bar_x, bar_y, fill_w, bar_h, bright_color)
        self.pager.rect(bar_x, bar_y, bar_w, bar_h, unselected_color)

        # Menu items below brightness
        items_start_y = bar_y + 28
        sound_label = "Sound: ON" if self.sound_enabled else "Sound: OFF"
        cat_label = "Categories: ON" if self.category_view else "Categories: OFF"
        boot_label = "Boot on Start: ON" if boot_enabled else "Boot on Start: OFF"
        items = [sound_label, cat_label, boot_label, "Back"]

        for i, item in enumerate(items):
            y = items_start_y + i * 22
            is_sel = (i + 1) == selected  # +1 because brightness is item 0
            color = selected_color if is_sel else unselected_color
            tw = self.pager.ttf_width(item, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item, color, self.font, self.item_fs)

        self.pager.flip()

    def show_settings(self):
        """Show the settings submenu with brightness, sound, categories, and boot toggle."""
        selected = 0  # 0=brightness, 1=sound, 2=categories, 3=boot, 4=back
        num_items = 5
        brightness = self.pager.get_brightness()
        if brightness < 0:
            brightness = 80

        while True:
            boot_enabled = self._is_boot_enabled()
            self._draw_settings(selected, brightness, boot_enabled)

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                selected = (selected - 1) % num_items
                self._beep()
            elif button & self.pager.BTN_DOWN:
                selected = (selected + 1) % num_items
                self._beep()
            elif button & self.pager.BTN_LEFT:
                if selected == 0:
                    brightness = max(5, brightness - 5)
                    self.pager.set_brightness(brightness)
                    self._beep()
            elif button & self.pager.BTN_RIGHT:
                if selected == 0:
                    brightness = min(100, brightness + 5)
                    self.pager.set_brightness(brightness)
                    self._beep()
            elif button & self.pager.BTN_A:
                if selected == 0:
                    pass  # Brightness uses left/right
                elif selected == 1:
                    # Toggle sound
                    self.sound_enabled = not self.sound_enabled
                    self._beep_select()
                elif selected == 2:
                    # Toggle category view
                    self.category_view = not self.category_view
                    self._beep_select()
                elif selected == 3:
                    # Toggle boot
                    self._beep_select()
                    if boot_enabled:
                        if self._uninstall_boot():
                            self._show_message("Boot disabled")
                        else:
                            self._show_message("Failed to disable")
                    else:
                        if self._install_boot():
                            self._show_message("Boot enabled")
                        else:
                            self._show_message("Failed to enable")
                elif selected == 4:
                    self._beep_select()
                    return
            elif button & self.pager.BTN_B:
                self._beep()
                return

    def cleanup(self):
        try:
            self.pager.clear(self.pager.BLACK)
            self.pager.flip()
            self.pager.cleanup()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
SETTINGS_PATH = "__settings__"


def launch_payload(payload_path):
    """Launch a payload and wait for exit."""
    try:
        result = subprocess.run(['sh', payload_path])
        return result.returncode
    except KeyboardInterrupt:
        return 0
    except Exception:
        return 1


def start_pager_service():
    """Start the pineapple pager service and exit."""
    try:
        subprocess.run(['/etc/init.d/pineapplepager', 'start'], timeout=10)
    except Exception:
        pass


def shutdown_pager():
    """Shutdown the pager."""
    try:
        subprocess.run(['poweroff'], timeout=5)
    except Exception:
        pass


def main():
    while True:
        menu = LauncherMenu()
        selection = menu.run()

        if selection is None or selection['path'] == '__pager_service__':
            menu.cleanup()
            start_pager_service()
            break
        elif selection['path'] == '__shutdown__':
            menu._show_message("Shutting down...")
            menu.cleanup()
            shutdown_pager()
            break
        elif selection['path'] == '__settings__':
            menu.show_settings()
            # Return to main menu after settings
            menu.cleanup()
            time.sleep(0.1)
        else:
            menu.cleanup()
            launch_payload(selection['path'])
            # Payload exited — loop back to launcher menu
            time.sleep(0.3)


if __name__ == '__main__':
    main()
