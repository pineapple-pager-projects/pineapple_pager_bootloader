# Pagerctl Bootloader

A boot launcher menu for the WiFi Pineapple Pager. Launch payloads directly using pagerctl — no Pineapple Pager UI required.

<p align="center">
  <img src="screenshots/main_flat.png" width="380" alt="Main Menu">
  <img src="screenshots/main_categories.png" width="380" alt="Category View">
</p>
<p align="center">
  <img src="screenshots/category_submenu.png" width="380" alt="Category Submenu">
  <img src="screenshots/settings.png" width="380" alt="Settings">
</p>

The bootloader background automatically matches your active Pineapple Pager UI theme. The screenshots above use the **Circuitry** theme. Here's the same bootloader with the **Wargames** theme:

<p align="center">
  <img src="screenshots/main_wargames.png" width="380" alt="Wargames Theme">
</p>

You can also set a custom background in `launcher_config.json` to use your own design regardless of the active Pager theme.

## What It Does

The bootloader bypasses the Pineapple Pager UI and launches payloads directly using `libpagerctl.so` for LCD rendering. It can run:

- **On boot** — replaces the Pineapple Pager UI as the default startup screen
- **As a payload** — launch from the Pager UI like any other payload (General > pagerctl_bootloader)

When a payload exits, you're returned to the bootloader menu. Select "Exit to Pager UI" to start the normal Pineapple Pager interface.

## Features

- Auto-discovers installed payloads from launch scripts
- Only shows payloads that are actually installed on the device
- Category view with toggle (groups payloads by type)
- Scrolling menu with UP/DOWN navigation
- Settings: brightness control, sound toggle, category view, boot on start
- All settings persist across reboots
- Themeable: custom background, fonts, colors
- Background defaults to the active Pineapple Pager theme
- Sound effects on navigation
- Shutdown and restart options

## Installation

### Option 1: Git Clone
```
git clone https://github.com/pineapple-pager-projects/pineapple_pager_bootloader.git pagerctl_bootloader
scp -r pagerctl_bootloader root@172.16.42.1:/root/payloads/user/general/
```

### Option 2: Download ZIP
1. Download the ZIP from GitHub
2. Extract and rename the folder to `pagerctl_bootloader`
3. Copy to the pager:
```
scp -r pagerctl_bootloader root@172.16.42.1:/root/payloads/user/general/
```

The directory **must** be named `pagerctl_bootloader` on the pager.

## Controls

| Button | Action |
|--------|--------|
| UP / DOWN | Navigate menu |
| GREEN | Select / confirm |
| RED | Back (in submenus) |
| LEFT / RIGHT | Adjust brightness (in Settings) |

## Boot on Start

Enable in **Settings > Boot on Start: ON** to have the bootloader run automatically when the pager powers on, bypassing the Pineapple Pager UI entirely.

When enabled, the bootloader installs an init script that runs before the Pineapple Pager service. Select "Exit to Pager UI" at any time to start the normal interface.

Disable with **Settings > Boot on Start: OFF** to restore normal boot behavior.

## Adding Payloads

Payloads are added by creating a launch script in the `scripts/` directory. The bootloader auto-discovers all `launch_*.sh` scripts and only shows them if the payload is actually installed.

### Creating a Launch Script

Create a file in `scripts/` named `launch_yourpayload.sh`:

```sh
#!/bin/sh
# Title: My Payload
# Requires: /root/payloads/user/category/mypayload
# Category: Reconnaissance
# Direct launcher — bypasses duckyscript commands

PAYLOAD_DIR="/root/payloads/user/category/mypayload"

cd "$PAYLOAD_DIR" || exit 1

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

python3 main.py

exit 0
```

### Required Metadata

| Tag | Required | Description |
|-----|----------|-------------|
| `# Title:` | Yes | Display name shown in the menu |
| `# Requires:` | Yes | Path to the payload directory — if this directory doesn't exist, the payload is hidden from the menu |
| `# Category:` | No | Category for grouped view (defaults to "Other"). Examples: `Reconnaissance`, `Games`, `Utilities` |

### Why Launch Scripts?

The Pineapple Pager normally runs `payload.sh` through its duckyscript engine, which provides commands like `LOG`, `WAIT_FOR_INPUT`, `START_SPINNER`, etc. These don't exist when running from the bootloader since the Pager service is stopped.

Launch scripts bypass all duckyscript commands and go straight to the payload's Python or binary entry point with the correct environment variables set.

### For C/Binary Payloads

If the payload is a compiled binary instead of Python:

```sh
#!/bin/sh
# Title: My Game
# Requires: /root/payloads/user/games/mygame
# Category: Games

PAYLOAD_DIR="/root/payloads/user/games/mygame"

cd "$PAYLOAD_DIR" || exit 1

export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR:$LD_LIBRARY_PATH"

/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.3

chmod +x ./mygame 2>/dev/null
./mygame

exit 0
```

## Theming

The bootloader uses the active Pineapple Pager theme's background by default (`alert_dialog_bg_term_blue.png`). Fonts and colors are configured in `launcher_config.json`.

### launcher_config.json

```json
{
    "title": "Bootloader",
    "show_title": true,
    "title_font": "fonts/title.TTF",
    "font": "fonts/menu.ttf",
    "title_font_size": 28,
    "item_font_size": 18,
    "bg_image": "images/custom_bg.png",
    "colors": {
        "title": [100, 200, 255],
        "selected": [0, 255, 0],
        "unselected": [255, 255, 255],
        "highlight_bg": [30, 50, 80]
    }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `title` | "Bootloader" | Title text displayed at the top |
| `show_title` | true | Set to `false` if title is baked into background image |
| `title_font` | fonts/title.TTF | Font for the title (relative to bootloader directory) |
| `font` | fonts/menu.ttf | Font for menu items |
| `title_font_size` | 28 | Title font size in pixels |
| `item_font_size` | 18 | Menu item font size in pixels |
| `bg_image` | (active theme) | Custom background image (480x222 PNG). If not set, uses the active Pager theme's background |
| `colors.title` | [100, 200, 255] | Title text color [R, G, B] |
| `colors.selected` | [0, 255, 0] | Selected menu item color |
| `colors.unselected` | [255, 255, 255] | Unselected menu item color |
| `colors.highlight_bg` | [30, 50, 80] | Highlight background (not currently used) |

### Custom Background

To use a custom background instead of the active Pager theme:

1. Create a 480x222 PNG image
2. Place it in the bootloader directory (e.g., `images/my_bg.png`)
3. Set `"bg_image": "images/my_bg.png"` in `launcher_config.json`
4. Optionally set `"show_title": false` if the title is baked into the image

## Persistent Settings

Settings are saved to `settings.json` and persist across reboots:

- **Brightness** — LCD brightness level
- **Sound** — Navigation beep on/off
- **Categories** — Category view on/off

## Included Launch Scripts

| Script | Title | Category | Requires |
|--------|-------|----------|----------|
| `launch_loki.sh` | Loki | Reconnaissance | `/root/payloads/user/reconnaissance/loki` |
| `launch_pagergotchi.sh` | PagerGotchi | Reconnaissance | `/root/payloads/user/reconnaissance/pagergotchi` |
| `launch_cyt.sh` | Chasing Your Tail | Reconnaissance | `/mmc/root/payloads/user/reconnaissance/cyt` |
| `launch_pagerpwn.sh` | PagerPwn | Reconnaissance | `/mmc/root/payloads/user/reconnaissance/PagerPwn` |
| `launch_ragnar.sh` | Ragnar | Reconnaissance | `/root/payloads/user/reconnaissance/pager_ragnar` |
| `launch_pageramp.sh` | PagerAmp | Utilities | `/root/payloads/user/utilities/pageramp` |
| `launch_wifman.sh` | WiFMan | Utilities | `/root/payloads/user/general/wifman` |
| `launch_tetris.sh` | Tetris | Games | `/root/payloads/user/games/tetris` |
| `launch_space_invaders.sh` | Space Invaders | Games | `/root/payloads/user/games/space_invaders` |
| `launch_hakanoid.sh` | Hakanoid | Games | `/root/payloads/user/games/hakanoid` |

Only payloads that are installed on the device will appear in the menu.

## Credits

- **Author**: brAinphreAk
- **WiFi Pineapple Pager**: Hak5
- **pagerctl**: libpagerctl.so by Hak5

## License

MIT License
