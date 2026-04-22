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
    'warning': [255, 180, 60],
}

PAGER_UI_ENTRY = {"name": "Exit to Pager UI", "path": "__pager_service__"}
SETTINGS_ENTRY = {"name": "Settings", "path": "__settings__"}
SHUTDOWN_ENTRY = {"name": "Shutdown", "path": "__shutdown__"}
RESTART_ENTRY = {"name": "Restart Bootloader", "path": "__restart__"}

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


SETTINGS_FILE = os.path.join(SCRIPT_DIR, 'settings.json')


def _default_auto_boot_path():
    """On first run, prefer pagerctl_home if it's installed. Point at
    its pagerctl.sh if present, else fall back to payload.sh."""
    home_dir = '/root/payloads/user/general/pagerctl_home'
    if not os.path.isdir(home_dir):
        return None
    for name in ('pagerctl.sh', 'payload.sh'):
        p = os.path.join(home_dir, name)
        if os.path.isfile(p):
            return p
    return None


def load_settings():
    """Load persistent settings from disk."""
    defaults = {
        'brightness': 80,
        'sound_enabled': True,
        'category_view': False,
        'auto_boot_path': None,
        'show_classic_payloads': False,
        # Fast boot skips the "wait for services to settle" pause
        # before launching the auto-boot payload. Off by default so
        # new users don't hit the 30-45s of background init that
        # makes games feel sluggish on first launch.
        'fast_boot': False,
    }
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    else:
        defaults['auto_boot_path'] = _default_auto_boot_path()
    return defaults


def save_settings(settings):
    """Save settings to disk."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Payload discovery
# ---------------------------------------------------------------------------
PAYLOADS_ROOT = '/mmc/root/payloads/user'

# Payloads that would fight us for the display if launched from the
# menu — the bootloader itself is already running. pagerctl_home is
# fine to launch from here (that's a common use case) so only the
# bootloader is excluded.
HIDDEN_PAYLOADS = frozenset({'pagerctl_bootloader'})


def _parse_header(script_path):
    """Read '# Title:' / '# Category:' from a payload entry script."""
    title = None
    category = None
    try:
        with open(script_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith('#'):
                    if line and not line.startswith('#') and title:
                        break
                    continue
                if line.startswith('# Title:'):
                    title = line[len('# Title:'):].strip()
                elif line.startswith('# Category:'):
                    category = line[len('# Category:'):].strip()
                if title and category:
                    break
    except Exception:
        pass
    return title, category


def discover_payloads():
    """Scan /mmc/root/payloads/user/<category>/<payload>/ for installed
    payloads. Each payload dir is expected to ship a pagerctl.sh
    (pagerctl-native launcher) — that's the supported path. A classic
    payload.sh is only included when Settings > Show Classic Payloads
    is enabled. Matches pagerctl_home's payload_browser behavior so
    both menus show the same entries."""
    payloads = []
    if not os.path.isdir(PAYLOADS_ROOT):
        return payloads

    show_classic = bool(load_settings().get('show_classic_payloads', False))

    for cat_name in sorted(os.listdir(PAYLOADS_ROOT)):
        cat_path = os.path.join(PAYLOADS_ROOT, cat_name)
        if not os.path.isdir(cat_path):
            continue
        category_display = cat_name.replace('_', ' ').title()
        for entry in sorted(os.listdir(cat_path)):
            if entry in HIDDEN_PAYLOADS:
                continue
            payload_dir = os.path.join(cat_path, entry)
            if not os.path.isdir(payload_dir):
                continue

            pagerctl_sh = os.path.join(payload_dir, 'pagerctl.sh')
            payload_sh = os.path.join(payload_dir, 'payload.sh')
            if os.path.isfile(pagerctl_sh):
                script_path = pagerctl_sh
            elif show_classic and os.path.isfile(payload_sh):
                script_path = payload_sh
            else:
                continue

            title, cat_override = _parse_header(script_path)
            title = title or entry
            category = cat_override or category_display

            payloads.append({
                'name': title,
                'path': script_path,
                'category': category,
            })

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
            'warning': config_colors.get('warning', DEFAULT_COLORS['warning']),
        }

        # Background image — config override, or active pager theme default
        bg = self.config.get('bg_image')
        if bg and os.path.isfile(resolve_path(bg)):
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
        self.show_settings_title = self.config.get('show_settings_title', True)
        self.show_category_title = self.config.get('show_category_title', True)

        # Per-screen backgrounds (optional overrides)
        cat_bg = self.config.get('category_bg_image')
        self.category_bg = resolve_path(cat_bg) if cat_bg and os.path.isfile(resolve_path(cat_bg)) else None
        settings_bg_cfg = self.config.get('settings_bg_image')
        self.settings_bg = resolve_path(settings_bg_cfg) if settings_bg_cfg and os.path.isfile(resolve_path(settings_bg_cfg)) else None
        self.title_fs = self.config.get('title_font_size', 28)
        self.item_fs = self.config.get('item_font_size', 18)

        # Build payload list
        if 'payloads' in self.config:
            self.payloads = list(self.config['payloads'])
        else:
            self.payloads = discover_payloads()

        # Load favorites from settings
        self.favorites = load_settings().get('favorites', [])

        # Sort: favorites first (in order), then the rest
        fav_payloads = []
        non_fav_payloads = []
        for p in self.payloads:
            if p['path'] in self.favorites:
                fav_payloads.append(p)
            else:
                non_fav_payloads.append(p)
        # Maintain favorites order
        fav_payloads.sort(key=lambda p: self.favorites.index(p['path']) if p['path'] in self.favorites else 999)
        self.payloads = fav_payloads + non_fav_payloads

        # Add settings, exit, and shutdown as last options
        self.payloads.append(SETTINGS_ENTRY)
        self.payloads.append(PAGER_UI_ENTRY)
        self.payloads.append(SHUTDOWN_ENTRY)
        self.payloads.append(RESTART_ENTRY)

        self.selected = 0
        self.scroll_offset = 0
        self.max_visible = 6

        # Load persistent settings
        settings = load_settings()
        self.sound_enabled = settings['sound_enabled']
        self.category_view = settings['category_view']
        self.auto_boot_path = settings.get('auto_boot_path')
        self.show_classic_payloads = bool(settings.get('show_classic_payloads', False))
        self.fast_boot = bool(settings.get('fast_boot', False))

        # Apply saved brightness
        try:
            self.pager.set_brightness(settings['brightness'])
        except Exception:
            pass

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
        start_y = 65
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
            # Add star for favorites
            is_fav = payload.get('path', '') in self.favorites
            label = f"* {payload['name']}" if is_fav else payload['name']
            tw = self.pager.ttf_width(label, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, label, color, self.font, self.item_fs)

        # Scroll indicators
        if self.scroll_offset > 0:
            self.pager.draw_ttf(SCREEN_W - 30, start_y - 15, "^", unselected_color, self.font, 14)
        if self.scroll_offset + visible_items < len(self.payloads):
            self.pager.draw_ttf(SCREEN_W - 30, start_y + (visible_items - 1) * item_height,
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
        """Show payloads within a category with scrolling. Returns selected payload or None for back."""
        selected = 0
        scroll_offset = 0
        max_vis = self.max_visible
        items = list(payloads)

        while True:
            # Draw with scrolling — use category bg if set, else main bg
            bg = self.category_bg or self.bg_image
            if bg and os.path.isfile(bg):
                try:
                    self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, bg)
                except Exception:
                    self.pager.clear(self.pager.BLACK)
            else:
                self.pager.clear(self.pager.BLACK)

            if self.font:
                title_color = self._rgb(self.colors['title'])
                selected_color = self._rgb(self.colors['selected'])
                unselected_color = self._rgb(self.colors['unselected'])

                if self.show_category_title:
                    tw = self.pager.ttf_width(category_name, self.title_font, self.title_fs)
                    self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, category_name, title_color, self.title_font, self.title_fs)

                item_height = 22
                start_y = 70
                visible = min(max_vis, len(items))

                if selected < scroll_offset:
                    scroll_offset = selected
                elif selected >= scroll_offset + visible:
                    scroll_offset = selected - visible + 1

                for i in range(visible):
                    idx = scroll_offset + i
                    if idx >= len(items):
                        break
                    y = start_y + i * item_height
                    is_sel = idx == selected
                    color = selected_color if is_sel else unselected_color
                    tw = self.pager.ttf_width(items[idx]['name'], self.font, self.item_fs)
                    self.pager.draw_ttf((SCREEN_W - tw) // 2, y, items[idx]['name'], color, self.font, self.item_fs)

                if scroll_offset > 0:
                    self.pager.draw_ttf(SCREEN_W - 30, start_y, "^", unselected_color, self.font, 14)
                if scroll_offset + visible < len(items):
                    self.pager.draw_ttf(SCREEN_W - 30, start_y + (visible - 1) * item_height, "v", unselected_color, self.font, 14)

            self.pager.flip()

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
            elif button & self.pager.BTN_RIGHT:
                # Toggle favorite on current payload
                payload = self.payloads[self.selected]
                path = payload.get('path', '')
                if path and not path.startswith('__'):
                    if path in self.favorites:
                        self.favorites.remove(path)
                    else:
                        self.favorites.append(path)
                    s = load_settings()
                    s['favorites'] = self.favorites
                    save_settings(s)
                    self._beep()
                    self.draw()
            elif button & self.pager.BTN_A:
                self._beep_select()
                return self.payloads[self.selected]

    def _run_category_view(self):
        """Run with category navigation."""
        all_payloads = [p for p in self.payloads if p.get('path') not in
             ('__pager_service__', '__settings__', '__shutdown__', '__restart__')]
        categories = group_by_category(all_payloads)
        cat_names = sorted(categories.keys())

        # Add Favorites category at top if there are any
        fav_payloads = [p for p in all_payloads if p.get('path') in self.favorites]
        menu_items = []
        if fav_payloads:
            menu_items.append({"name": "Favorites", "path": "__category__"})
            categories["Favorites"] = fav_payloads
        menu_items.extend([{"name": cat, "path": "__category__"} for cat in cat_names])
        menu_items.append(SETTINGS_ENTRY)
        menu_items.append(PAGER_UI_ENTRY)
        menu_items.append(SHUTDOWN_ENTRY)
        menu_items.append(RESTART_ENTRY)

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
                start_y = 65
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
                    label = item['name']
                    tw = self.pager.ttf_width(label, self.font, self.item_fs)
                    self.pager.draw_ttf((SCREEN_W - tw) // 2, y, label, color, self.font, self.item_fs)

                if scroll_offset > 0:
                    self.pager.draw_ttf(SCREEN_W - 30, start_y - 15, "^", unselected_color, self.font, 14)
                if scroll_offset + visible < len(menu_items):
                    self.pager.draw_ttf(SCREEN_W - 30, start_y + (visible - 1) * item_height, "v", unselected_color, self.font, 14)

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
        return os.path.exists("/etc/rc.d/S16pagerctl_bootloader")

    def _read_launcher_title(self, path):
        """Return the '# Title:' value from a launcher script, or basename."""
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('# Title:'):
                        return line[len('# Title:'):].strip()
        except Exception:
            pass
        return os.path.splitext(os.path.basename(path))[0]

    def _auto_boot_label(self):
        if not self.auto_boot_path:
            return "Auto Boot: OFF"
        return f"Auto Boot: {self._read_launcher_title(self.auto_boot_path)}"

    def _save_current_settings(self, **overrides):
        """Persist every field the settings screens can mutate. Takes
        optional overrides so individual handlers can update a single
        value without rebuilding the whole dict inline."""
        data = {
            'brightness': overrides.get('brightness',
                                         self.pager.get_brightness()),
            'sound_enabled': self.sound_enabled,
            'category_view': self.category_view,
            'auto_boot_path': self.auto_boot_path,
            'show_classic_payloads': self.show_classic_payloads,
            'fast_boot': self.fast_boot,
        }
        data.update(overrides)
        save_settings(data)

    def _attempt_auto_boot(self):
        """If auto_boot_path is set and valid, run a cancelable countdown
        and return a payload dict to launch. B cancels. Missing target
        clears the setting and falls through. Returns None to skip."""
        path = self.auto_boot_path
        if not path:
            return None
        if not os.path.isfile(path):
            self._show_message("Auto-boot target missing")
            self.auto_boot_path = None
            s = load_settings()
            s['auto_boot_path'] = None
            save_settings(s)
            return None

        title = self._read_launcher_title(path)
        countdown_seconds = 2

        try:
            self.pager.clear_input_events()
        except Exception:
            pass

        start = time.time()
        deadline = start + countdown_seconds
        last_shown = None

        while True:
            remaining_f = deadline - time.time()
            if remaining_f <= 0:
                break
            remaining = int(remaining_f) + 1  # ceil for friendly countdown
            if remaining != last_shown:
                self._draw_auto_boot_screen(title, remaining)
                last_shown = remaining

            try:
                _, pressed, _ = self.pager.poll_input()
            except Exception:
                pressed = 0
            if pressed & self.pager.BTN_B:
                self._beep()
                return None
            time.sleep(0.05)

        # Fast Boot OFF: after the countdown, hold on the "warming up"
        # screen while background services finish coming up. Makes the
        # 30-45s of first-boot sluggishness visible and controlled
        # instead of the user feeling that the game is frozen.
        if not self.fast_boot:
            self._wait_for_services_ready()

        return {'name': title, 'path': path}

    # Ordered check list for the readiness wait. Each entry is a tuple
    # (label, check_fn). First check that fails is what we report on
    # the progress screen so the user sees which service they're
    # waiting on. Kept short so any single check doesn't dominate the
    # timeout.
    _READINESS_CHECKS = (
        ('network', lambda: os.path.exists('/sys/class/net/br-lan/operstate')),
        ('wireless', lambda: os.path.exists('/sys/class/net/wlan0')),
        ('hostapd', lambda: subprocess.run(
            ['pgrep', '-x', 'hostapd'], capture_output=True).returncode == 0),
    )

    def _services_ready(self):
        """Return (ready, current_step_label). ready=True when all
        checks pass. When False, label names the step we're blocked
        on — shown under the progress bar."""
        for label, check in self._READINESS_CHECKS:
            try:
                if not check():
                    return False, label
            except Exception:
                return False, label
        return True, 'ready'

    def _wait_for_services_ready(self, timeout=45):
        """Poll readiness checks with a visible progress bar. Bails
        after `timeout` seconds even if not everything came up —
        better to launch a slightly-slow game than hang forever on a
        quirky boot."""
        start = time.time()
        last_drawn = -1
        while True:
            elapsed = time.time() - start
            ready, step = self._services_ready()
            if ready or elapsed >= timeout:
                return
            progress = min(1.0, elapsed / timeout)
            # Only redraw when the percentage advances a visible step
            # so we don't burn CPU on the wait screen itself.
            pct = int(progress * 100)
            if pct != last_drawn:
                self._draw_services_screen(step, pct)
                last_drawn = pct
            try:
                _, pressed, _ = self.pager.poll_input()
            except Exception:
                pressed = 0
            if pressed & self.pager.BTN_B:
                # Cancel = launch now anyway. Same effect as Fast Boot
                # but ad-hoc for one boot.
                return
            time.sleep(0.2)

    def _draw_services_screen(self, step, pct):
        """Progress bar screen shown while waiting for services."""
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

        header = "Warming up services..."
        tw = self.pager.ttf_width(header, self.title_font, self.title_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 40, header,
                             title_color, self.title_font, self.title_fs)

        bar_x = 60
        bar_y = 110
        bar_w = 360
        bar_h = 18
        self.pager.fill_rect(bar_x, bar_y, bar_w, bar_h, self._rgb([40, 40, 40]))
        fill_w = int(bar_w * pct / 100)
        self.pager.fill_rect(bar_x, bar_y, fill_w, bar_h, selected_color)
        self.pager.rect(bar_x, bar_y, bar_w, bar_h, unselected_color)

        step_line = f"waiting for {step}  ({pct}%)"
        tw = self.pager.ttf_width(step_line, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, bar_y + bar_h + 14,
                             step_line, selected_color, self.font, self.item_fs)

        hint = "B = skip"
        tw = self.pager.ttf_width(hint, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, bar_y + bar_h + 42,
                             hint, unselected_color, self.font, self.item_fs)
        self.pager.flip()

    def _draw_auto_boot_screen(self, title, remaining):
        """Render one frame of the auto-boot countdown."""
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

        header = "Auto Boot"
        tw = self.pager.ttf_width(header, self.title_font, self.title_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, header, title_color, self.title_font, self.title_fs)

        line1 = f"Launching: {title}"
        tw = self.pager.ttf_width(line1, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 90, line1, selected_color, self.font, self.item_fs)

        line2 = f"in {remaining}s..."
        tw = self.pager.ttf_width(line2, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 120, line2, selected_color, self.font, self.item_fs)

        line3 = "B = cancel"
        tw = self.pager.ttf_width(line3, self.font, self.item_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 160, line3, unselected_color, self.font, self.item_fs)

        # When Fast Boot is on the launch fires before services have
        # finished coming up — warn so the user doesn't misread the
        # first-minute sluggishness as a crash.
        if self.fast_boot:
            warn_color = self._rgb(self.colors['warning'])
            warn = "Fast Boot: perf may be reduced 30-45s"
            tw = self.pager.ttf_width(warn, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 190, warn,
                                 warn_color, self.font, self.item_fs)

        self.pager.flip()

    def _show_auto_boot_picker(self):
        """Let user pick which payload auto-boots. Saves immediately on A."""
        items = [{'name': 'None (disabled)', 'path': None}]
        for p in discover_payloads():
            items.append({'name': p['name'], 'path': p['path']})

        # Start on currently-selected entry if present
        selected = 0
        for i, it in enumerate(items):
            if it['path'] == self.auto_boot_path:
                selected = i
                break
        scroll_offset = 0
        max_vis = self.max_visible

        while True:
            bg = self.settings_bg or self.bg_image
            if bg and os.path.isfile(bg):
                try:
                    self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, bg)
                except Exception:
                    self.pager.clear(self.pager.BLACK)
            else:
                self.pager.clear(self.pager.BLACK)

            title_color = self._rgb(self.colors['title'])
            selected_color = self._rgb(self.colors['selected'])
            unselected_color = self._rgb(self.colors['unselected'])

            tw = self.pager.ttf_width("Auto Boot", self.title_font, self.title_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, "Auto Boot", title_color, self.title_font, self.title_fs)

            item_height = 22
            start_y = 70
            visible = min(max_vis, len(items))

            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + visible:
                scroll_offset = selected - visible + 1

            for i in range(visible):
                idx = scroll_offset + i
                if idx >= len(items):
                    break
                y = start_y + i * item_height
                is_sel = idx == selected
                color = selected_color if is_sel else unselected_color
                tw = self.pager.ttf_width(items[idx]['name'], self.font, self.item_fs)
                self.pager.draw_ttf((SCREEN_W - tw) // 2, y, items[idx]['name'], color, self.font, self.item_fs)

            if scroll_offset > 0:
                self.pager.draw_ttf(SCREEN_W - 30, start_y, "^", unselected_color, self.font, 14)
            if scroll_offset + visible < len(items):
                self.pager.draw_ttf(SCREEN_W - 30, start_y + (visible - 1) * item_height, "v", unselected_color, self.font, 14)

            self.pager.flip()

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                selected = (selected - 1) % len(items)
                self._beep()
            elif button & self.pager.BTN_DOWN:
                selected = (selected + 1) % len(items)
                self._beep()
            elif button & self.pager.BTN_A:
                self._beep_select()
                self.auto_boot_path = items[selected]['path']
                s = load_settings()
                s['auto_boot_path'] = self.auto_boot_path
                save_settings(s)
                return
            elif button & self.pager.BTN_B:
                self._beep()
                return

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
        start_y = 65
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
        """Install bootloader (START=16) and boot splash (START=00)."""
        # Boot splash — kills default animation, plays custom frames
        boot_splash_script = '''#!/bin/sh /etc/rc.common
USE_PROCD=1
START=00
start_service() {
    [ -f /etc/rc.d/S16pagerctl_bootloader ] || return 0
    for i in 1 2 3 4 5; do
        killall boot_animation 2>/dev/null
        pgrep -x boot_animation >/dev/null 2>&1 || break
        sleep 0.1
    done
    FRAME_DIR="/overlay/upper/boot_frames"
    [ -d "$FRAME_DIR" ] || return 0
    (
        FRAMES=$(ls "$FRAME_DIR"/*.fb 2>/dev/null | sort -V)
        [ -z "$FRAMES" ] && exit 0
        while true; do
            for f in $FRAMES; do
                dd if="$f" of=/dev/fb0 conv=nocreat 2>/dev/null
                sleep 0.55
            done
        done
    ) &
    echo $! > /tmp/custom_boot_anim.pid
}
stop_service() {
    [ -f /tmp/custom_boot_anim.pid ] && kill $(cat /tmp/custom_boot_anim.pid) 2>/dev/null
    rm -f /tmp/custom_boot_anim.pid
}
'''
        # Bootloader — launches menu after mmc is available
        bootloader_script = '''#!/bin/sh /etc/rc.common
USE_PROCD=1
START=16
start_service() {
    killall boot_animation 2>/dev/null
    [ -f /tmp/custom_boot_anim.pid ] && kill $(cat /tmp/custom_boot_anim.pid) 2>/dev/null
    rm -f /tmp/custom_boot_anim.pid
    /etc/init.d/pineapplepager disable 2>/dev/null
    /etc/init.d/pineapplepager stop 2>/dev/null
    LAUNCHER_DIR=/root/payloads/user/general/pagerctl_bootloader
    [ -f "$LAUNCHER_DIR/launch_menu.py" ] || { /etc/init.d/pineapplepager enable; /etc/init.d/pineapplepager start; return; }
    export PATH=/mmc/usr/bin:$PATH
    export PYTHONPATH=$LAUNCHER_DIR/lib:$LAUNCHER_DIR
    export LD_LIBRARY_PATH=/mmc/usr/lib:$LAUNCHER_DIR/lib
    export PAGERCTL_BOOTLOADER_MODE=boot
    cd $LAUNCHER_DIR
    python3 launch_menu.py &
}
stop_service() {
    return 0
}
'''
        try:
            # Convert boot frame PNGs to .fb if boot_frames/ has PNGs
            boot_frames_dir = os.path.join(SCRIPT_DIR, 'boot_frames')
            if os.path.isdir(boot_frames_dir):
                pngs = [f for f in os.listdir(boot_frames_dir) if f.endswith('.png')]
                if pngs:
                    self._show_message("Converting boot frames...", 0.5)
                    converter = os.path.join(SCRIPT_DIR, 'png2fb.py')
                    if os.path.isfile(converter):
                        subprocess.run(['python3', converter], capture_output=True, timeout=30)

            # Install boot splash (START=00)
            splash_path = "/etc/init.d/boot_splash"
            with open(splash_path, 'w') as f:
                f.write(boot_splash_script)
            os.chmod(splash_path, 0o755)
            splash_symlink = "/etc/rc.d/S00boot_splash"
            if os.path.exists(splash_symlink):
                os.remove(splash_symlink)
            os.symlink("../init.d/boot_splash", splash_symlink)

            # Install bootloader (START=16)
            with open(INIT_SCRIPT_PATH, 'w') as f:
                f.write(bootloader_script)
            os.chmod(INIT_SCRIPT_PATH, 0o755)
            bl_symlink = "/etc/rc.d/S16pagerctl_bootloader"
            if os.path.exists(bl_symlink):
                os.remove(bl_symlink)
            os.symlink("../init.d/pagerctl_bootloader", bl_symlink)

            # Remove old symlink if exists
            old_symlink = "/etc/rc.d/S49pagerctl_bootloader"
            if os.path.exists(old_symlink):
                os.remove(old_symlink)

            # Disable pager service
            pager_symlink = "/etc/rc.d/S50pineapplepager"
            if os.path.exists(pager_symlink):
                os.remove(pager_symlink)

            return True
        except Exception:
            return False

    def _uninstall_boot(self):
        """Remove bootloader and boot splash from boot, restore pager service."""
        try:
            # Remove boot splash
            for path in ["/etc/rc.d/S00boot_splash", "/etc/init.d/boot_splash"]:
                if os.path.exists(path):
                    os.remove(path)

            # Remove bootloader symlinks and init script
            for path in ["/etc/rc.d/S16pagerctl_bootloader", "/etc/rc.d/S49pagerctl_bootloader"]:
                if os.path.exists(path):
                    os.remove(path)
            if os.path.isfile(INIT_SCRIPT_PATH):
                os.remove(INIT_SCRIPT_PATH)

            # Re-enable pager service
            pager_symlink = "/etc/rc.d/S50pineapplepager"
            if not os.path.exists(pager_symlink):
                os.symlink("../init.d/pineapplepager", pager_symlink)

            return True
        except Exception:
            return False

    def _draw_settings(self, selected, brightness, boot_enabled):
        """Draw the settings screen with brightness bar."""
        # Use settings bg if set, else main bg
        bg = self.settings_bg or self.bg_image
        if bg and os.path.isfile(bg):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, bg)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])

        # Title
        if self.show_settings_title:
            tw = self.pager.ttf_width("Settings", self.title_font, self.title_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, "Settings", title_color, self.title_font, self.title_fs)

        # Brightness bar (item 0)
        bar_y = 82
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
        classic_label = ("Classic Payloads: ON" if self.show_classic_payloads
                         else "Classic Payloads: OFF")
        auto_label = "Auto Boot..."
        items = [sound_label, cat_label, classic_label, auto_label]

        for i, item in enumerate(items):
            y = items_start_y + i * 22
            is_sel = (i + 1) == selected  # +1 because brightness is item 0
            color = selected_color if is_sel else unselected_color
            tw = self.pager.ttf_width(item, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item, color, self.font, self.item_fs)

        self.pager.flip()

    def show_settings(self):
        """Show the settings submenu. Auto-boot related toggles live
        one level deeper — see _show_autoboot_submenu."""
        selected = 0  # 0=brightness, 1=sound, 2=categories, 3=classic, 4=auto-boot submenu
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
                    self._save_current_settings(brightness=brightness)
                    self._beep()
            elif button & self.pager.BTN_RIGHT:
                if selected == 0:
                    brightness = min(100, brightness + 5)
                    self.pager.set_brightness(brightness)
                    self._save_current_settings(brightness=brightness)
                    self._beep()
            elif button & self.pager.BTN_A:
                if selected == 0:
                    pass  # Brightness uses left/right
                elif selected == 1:
                    self.sound_enabled = not self.sound_enabled
                    self._save_current_settings(brightness=brightness)
                    self._beep_select()
                elif selected == 2:
                    self.category_view = not self.category_view
                    self._save_current_settings(brightness=brightness)
                    self._beep_select()
                elif selected == 3:
                    self.show_classic_payloads = not self.show_classic_payloads
                    self._save_current_settings(brightness=brightness)
                    self._beep_select()
                elif selected == 4:
                    self._beep_select()
                    self._show_autoboot_submenu(brightness)
            elif button & self.pager.BTN_B:
                self._beep()
                return

    def _draw_autoboot_submenu(self, selected, boot_enabled):
        """Render the Auto Boot submenu. Three rows: toggle for whether
        the bootloader runs at all on power-on, picker for the program
        it auto-launches, and Fast Boot toggle."""
        bg = self.settings_bg or self.bg_image
        if bg and os.path.isfile(bg):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, bg)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])

        if self.show_settings_title:
            tw = self.pager.ttf_width("Auto Boot", self.title_font, self.title_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, "Auto Boot",
                                 title_color, self.title_font, self.title_fs)

        autostart_label = ("Autostart Bootloader: ON" if boot_enabled
                            else "Autostart Bootloader: OFF")
        program_label = f"Autostart Program: {self._read_launcher_title(self.auto_boot_path)}" \
            if self.auto_boot_path else "Autostart Program: None"
        fast_label = "Fast Boot: ON" if self.fast_boot else "Fast Boot: OFF"
        items = [autostart_label, program_label, fast_label]

        items_start_y = 82
        for i, item in enumerate(items):
            y = items_start_y + i * 28
            color = selected_color if i == selected else unselected_color
            tw = self.pager.ttf_width(item, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item,
                                 color, self.font, self.item_fs)

        self.pager.flip()

    def _show_autoboot_submenu(self, brightness):
        """Submenu for autostart + fast-boot toggles. Brightness is
        passed through so the shared _save_current_settings snapshot
        persists the live value rather than re-reading from hardware."""
        selected = 0
        num_items = 3
        while True:
            boot_enabled = self._is_boot_enabled()
            self._draw_autoboot_submenu(selected, boot_enabled)
            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                selected = (selected - 1) % num_items
                self._beep()
            elif button & self.pager.BTN_DOWN:
                selected = (selected + 1) % num_items
                self._beep()
            elif button & self.pager.BTN_A:
                self._beep_select()
                if selected == 0:
                    # Autostart Bootloader — install / uninstall the
                    # START=16 symlink. _install_boot / _uninstall_boot
                    # already handle the symlink + disable pineapplepager.
                    if boot_enabled:
                        if self._uninstall_boot():
                            self._show_message("Autostart disabled")
                        else:
                            self._show_message("Failed to disable")
                    else:
                        if self._install_boot():
                            self._show_message("Autostart enabled")
                        else:
                            self._show_message("Failed to enable")
                elif selected == 1:
                    self._show_auto_boot_picker()
                    self._save_current_settings(brightness=brightness)
                elif selected == 2:
                    new_val = not self.fast_boot
                    # Show the performance warning only when turning
                    # ON — turning OFF just re-enables the safe default.
                    if new_val and not self._confirm_fast_boot():
                        continue
                    self.fast_boot = new_val
                    self._save_current_settings(brightness=brightness)
            elif button & self.pager.BTN_B:
                self._beep()
                return

    def _confirm_fast_boot(self):
        """Warn the user before enabling Fast Boot. Returns True if
        they press A to confirm, False on B. Keeps the warning on screen
        until acknowledged so it can't be dismissed accidentally."""
        lines = [
            "Fast Boot enabled.",
            "Warning: may have performance",
            "issues for the first 30-45",
            "seconds while services start.",
            "",
            "B = cancel   A = enable",
        ]
        bg = self.settings_bg or self.bg_image
        if bg and os.path.isfile(bg):
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, bg)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)
        title_color = self._rgb(self.colors['title'])
        selected_color = self._rgb(self.colors['selected'])
        unselected_color = self._rgb(self.colors['unselected'])
        tw = self.pager.ttf_width("Fast Boot", self.title_font, self.title_fs)
        self.pager.draw_ttf((SCREEN_W - tw) // 2, 22, "Fast Boot",
                             title_color, self.title_font, self.title_fs)
        y = 70
        for i, line in enumerate(lines):
            color = selected_color if i == 0 else unselected_color
            tw = self.pager.ttf_width(line, self.font, self.item_fs)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, y, line,
                                 color, self.font, self.item_fs)
            y += 22
        self.pager.flip()
        while True:
            btn = self.pager.wait_button()
            if btn & self.pager.BTN_A:
                return True
            if btn & self.pager.BTN_B:
                return False

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
    menu = LauncherMenu()

    # Auto-boot fires only at cold boot (env var set by init script),
    # never when the bootloader is launched manually from the pager UI.
    if os.environ.get('PAGERCTL_BOOTLOADER_MODE') == 'boot':
        auto = menu._attempt_auto_boot()
        if auto is not None:
            menu.cleanup()
            launch_payload(auto['path'])
            time.sleep(0.3)
            menu = LauncherMenu()

    while True:
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
        elif selection['path'] == '__restart__':
            menu._show_message("Restarting...")
            menu.cleanup()
            time.sleep(0.3)
            # Re-exec the process so code changes take effect
            os.execv(sys.executable, [sys.executable] + sys.argv)
        elif selection['path'] == '__settings__':
            menu.show_settings()
            # Settings returns here — menu object keeps all state
        else:
            menu.cleanup()
            launch_payload(selection['path'])
            # Payload exited — recreate menu (pagerctl needs reinit)
            # Settings load from disk automatically
            time.sleep(0.3)
            menu = LauncherMenu()


if __name__ == '__main__':
    main()
