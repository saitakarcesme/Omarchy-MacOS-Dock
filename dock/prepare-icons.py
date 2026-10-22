#!/usr/bin/env python3
"""Fit installed artwork to a consistent dock silhouette; never redraw logos."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse
import json
import shutil
import subprocess
import sys
import tempfile

SIZE = 512
VERSION = 3
CACHE = Path.home() / '.cache/classic-dock/icons'
# Presentation preferences only: source artwork still comes from DesktopEntries.
STYLES = {
    'google-chrome': ('#fafafa', .86),
    'discord': ('#5662f6', .73),
    'spotify': ('#151515', .86),
    'com.microsoft.VSCode': ('#fafafa', .82),
    'localsend': ('#183b3c', .84),
}


def magick(*args):
    return subprocess.check_output(['magick', *map(str, args)], timeout=15)


def prepare(app):
    url = urlparse(app['source'])
    if url.scheme != 'file':
        return None
    source = Path(unquote(url.path))
    stat = source.stat()
    style = STYLES.get(app['id'], ('#f4f4f5', .78))
    key = sha256(json.dumps([str(source), stat.st_mtime_ns, stat.st_size,
                             VERSION, style]).encode()).hexdigest()[:24]
    dest = CACHE / (key + '.png')
    meta = CACHE / (key + '.json')
    if dest.exists() and meta.exists():
        return json.loads(meta.read_text())

    if app['id'] == 'discord':
        # The Linux icon embeds the white brand mark in a blue circle. Extract
        # that original mark before fitting it; adding a square behind the whole
        # circle gives the logo two sets of margins. Keep the original eye holes.
        CACHE.mkdir(parents=True, exist_ok=True)
        mark = CACHE / (key + '-mark.png')
        magick(source, '-alpha', 'on', '-channel', 'A', '-fx',
               'a * max(0, min(1, (r - 0.337254902) / 0.662745098))',
               '+channel', '-fill', 'white', '-colorize', '100', mark)
        source = mark

    # Inspect a small raster for silhouette coverage, ignoring faint shadows.
    raw = magick('-background', 'none', source, '-resize', '128x128',
                 '-gravity', 'center', '-extent', '128x128', '-depth', 8, 'rgba:-')
    occupied = [(i % 128, i // 128) for i, a in enumerate(raw[3::4]) if a > 100]
    if not occupied:
        return None
    x0, y0 = min(x for x, y in occupied), min(y for x, y in occupied)
    x1, y1 = max(x for x, y in occupied), max(y for x, y in occupied)
    w, h = x1-x0+1, y1-y0+1
    coverage = len(occupied)/(w*h)
    plated = coverage >= .87 and .88 <= w/h <= 1.14
    background, scale = style
    if background == 'edge':
        # Extend the actual icon's rim colour, avoiding a second visible circle.
        edge = [tuple(raw[(y*128+x)*4:(y*128+x)*4+3]) for x, y in occupied
                if y < y0+h*.22 and raw[(y*128+x)*4+3] > 240]
        rgb = Counter(edge).most_common(1)[0][0] if edge else (88, 101, 242)
        background = '#%02x%02x%02x' % rgb
    if not plated and app['id'] not in STYLES:
        # A light monochrome logo needs contrast on its automatically added plate.
        colors = [raw[i:i+3] for i in range(0, len(raw), 4) if raw[i+3] > 200]
        if colors and sum(min(c) > 200 for c in colors)/len(colors) > .65:
            background = '#303238'

    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
        tmp = Path(tmp)
        art, mask, composed = tmp/'art.png', tmp/'mask.png', tmp/'composed.png'
        # Normalise transparent padding at high resolution, retaining real detail.
        dimensions = magick('-background', 'none', source, '-format', '%w %h', 'info:').decode().split()
        sw, sh = map(int, dimensions)
        factor = min(128/sw, 128/sh)
        ox, oy = (128-sw*factor)/2, (128-sh*factor)/2
        left, top = max(0, round((x0-ox)/factor)), max(0, round((y0-oy)/factor))
        right, bottom = min(sw, round((x1+1-ox)/factor)), min(sh, round((y1+1-oy)/factor))
        target = SIZE if plated else round(SIZE*scale)
        magick('-background', 'none', source, '-crop', f'{right-left}x{bottom-top}+{left}+{top}',
               '+repage', '-resize', f'{target}x{target}', art)
        # Smooth, continuous corner transition shared by every dock icon.
        path = ('M 256,0 C 370,0 427,0 466,46 C 512,85 512,142 512,256 '
                'C 512,370 512,427 466,466 C 427,512 370,512 256,512 '
                'C 142,512 85,512 46,466 C 0,427 0,370 0,256 '
                'C 0,142 0,85 46,46 C 85,0 142,0 256,0 Z')
        magick('-size', '512x512', 'xc:none', '-fill', 'white', '-draw', f"path '{path}'", mask)
        magick('-size', '512x512', 'xc:none' if plated else 'xc:'+background,
               art, '-gravity', 'center', '-compose', 'over', '-composite', composed)
        if plated and coverage < .999:
            # Keep an existing frame intact: a new mask would cut its border.
            shutil.copyfile(composed, dest)
        else:
            magick(composed, mask, '-alpha', 'on', '-compose', 'DstIn', '-composite', dest)
    result = {'source': dest.as_uri(), 'mode': 'existing-plate' if plated else 'added-plate',
              'coverage': round(coverage, 3), 'background': None if plated else background}
    meta.write_text(json.dumps(result))
    return result


if __name__ == '__main__':
    result = {}
    for app in json.loads(sys.argv[1]):
        try:
            prepared = prepare(app)
            if prepared:
                result[app['source']] = prepared
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"Icon preparation {app.get('id')}: {error}", file=sys.stderr)
    print(json.dumps(result))
