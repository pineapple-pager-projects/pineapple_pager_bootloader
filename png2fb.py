#!/usr/bin/env python3
"""Convert PNG images to raw RGB565 framebuffer format for the Pager boot screen.
Uses pagerctl to render the PNG, then reads the framebuffer.
No PIL/Pillow required — uses the pager's own rendering pipeline.

Usage: python3 png2fb.py input.png output.fb [rotation]
  rotation: 0=portrait (default), 270=landscape-to-portrait
"""

import sys
import os
import struct

# Use pagerctl to render PNG and capture framebuffer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

from pagerctl import Pager


def png_to_fb(png_path, fb_path, rotation=0):
    """Render a PNG using pagerctl and save the raw framebuffer."""
    p = Pager()
    p.init()
    p.set_rotation(rotation)

    w = p.width
    h = p.height

    # Clear and draw the image
    p.clear(p.BLACK)
    p.draw_image_file_scaled(0, 0, w, h, png_path)
    p.flip()

    # Read framebuffer directly
    try:
        with open('/dev/fb0', 'rb') as fb:
            data = fb.read(222 * 480 * 2)  # Full framebuffer: 222x480 RGB565
    except Exception as e:
        print(f"Error reading framebuffer: {e}")
        p.cleanup()
        return False

    with open(fb_path, 'wb') as f:
        f.write(data)

    p.cleanup()
    return True


def convert_boot_frames(src_dir, dst_dir):
    """Convert all frameN.png files to N.fb in dst_dir."""
    os.makedirs(dst_dir, exist_ok=True)

    # Find all frame files
    frames = []
    for f in sorted(os.listdir(src_dir)):
        if f.startswith('frame') and f.endswith('.png'):
            frames.append(f)

    if not frames:
        print("No frame*.png files found")
        return False

    print(f"Converting {len(frames)} frames...")

    for f in frames:
        # Extract number from filename (frame1.png -> 1)
        num = ''.join(c for c in f.replace('.png', '').replace('frame', '') if c.isdigit())
        if not num:
            continue

        src = os.path.join(src_dir, f)
        dst = os.path.join(dst_dir, f"{num}.fb")

        print(f"  {f} -> {num}.fb ...", end=" ")

        # Render at rotation 270 (landscape PNG -> portrait framebuffer)
        if png_to_fb(src, dst, rotation=270):
            size = os.path.getsize(dst)
            print(f"OK ({size} bytes)")
        else:
            print("FAILED")
            return False

    return True


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        rotation = int(sys.argv[3]) if len(sys.argv) > 3 else 270
        png_to_fb(sys.argv[1], sys.argv[2], rotation)
    else:
        # Default: convert boot_frames/ -> /overlay/upper/boot_frames/
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boot_frames')
        dst = '/overlay/upper/boot_frames'
        convert_boot_frames(src, dst)
