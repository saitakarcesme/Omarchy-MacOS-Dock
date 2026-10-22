#!/usr/bin/env python3
"""Resolve installed application artwork, preferring vectors and large originals."""
from pathlib import Path
import json, os, struct

home = Path.home()
roots = [home/'.local/share/icons', home/'.icons', Path('/usr/local/share/icons/hicolor'), Path('/usr/share/icons/hicolor'), Path('/usr/share/pixmaps')]
for directory in os.environ.get('XDG_DATA_DIRS', '').split(':'):
    if directory:
        candidate = Path(directory)/'icons/hicolor'
        if candidate not in roots: roots.append(candidate)
result, scores = {}, {}
for root in roots:
    if not root.is_dir(): continue
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in ('.svg', '.png', '.xpm'): continue
        # Do not accidentally select a similarly named toolbar/action icon.
        if 'hicolor' in p.parts and 'apps' not in p.parts: continue
        try:
            if p.suffix == '.svg': score = 100000
            elif p.suffix == '.png':
                with p.open('rb') as f: header = f.read(24)
                if header[:8] != b'\x89PNG\r\n\x1a\n': continue
                width, height = struct.unpack('>II', header[16:24])
                score = min(width, height)
            else: score = 1
        except (OSError, ValueError, struct.error): continue
        key = p.stem
        if score > scores.get(key, -1):
            scores[key] = score
            result[key] = str(p)
print(json.dumps(result))
