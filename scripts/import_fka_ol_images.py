#!/usr/bin/env python3
"""Put a visible image on EVERY OL archive card using Google Images.

The site no longer depends on Football Kit Archive pages for displaying images.
For each reference in data/ol-archive.json, search Google Images and save the
first usable Google thumbnail locally. This is deliberately simple and robust:
even if an archive page shows a CAPTCHA, the local image still renders.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ARCHIVE = Path('data/ol-archive.json')
OUT = Path('assets/kits/google')
MANIFEST = Path('data/google-kit-images.json')
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST.parent.mkdir(parents=True, exist_ok=True)

S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
})


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-') or 'kit'


def google_images(query):
    url = 'https://www.google.com/search?tbm=isch&hl=en&q=' + quote(query)
    r = S.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    out = []
    for img in soup.find_all('img'):
        src = img.get('src') or ''
        if src.startswith('https://encrypted-tbn0.gstatic.com/images'):
            out.append(src)
    return out


def save_image(url, dest):
    r = S.get(url, timeout=30)
    r.raise_for_status()
    data = r.content
    if len(data) < 1500:
        return False
    dest.write_bytes(data)
    return True


def main():
    archive = json.loads(ARCHIVE.read_text(encoding='utf-8'))
    total = sum(len(kits) for kits in archive.values())
    records = []
    count = 0

    for season, kits in archive.items():
        for kit_type in kits:
            count += 1
            key = f'{season}-{kit_type}'
            name = f'OL {season} {kit_type}'
            query = f'Olympique Lyonnais {season} {kit_type} football shirt jersey'
            dest = OUT / (slug(key) + '.jpg')
            ok = dest.exists() and dest.stat().st_size > 1500

            if not ok:
                try:
                    for candidate in google_images(query)[:10]:
                        try:
                            if save_image(candidate, dest):
                                ok = True
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f'GOOGLE ERROR [{count}/{total}] {name}: {e}')

            records.append({
                'id': key,
                'season': season,
                'name': name,
                'type': kit_type,
                'image': str(dest).replace('\\', '/') if ok else None,
                'source': 'Google Images',
                'query': query
            })
            print(f'[{count}/{total}] {"OK" if ok else "NO IMAGE"} {name}')
            time.sleep(0.35)

    MANIFEST.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    success = sum(1 for x in records if x['image'])
    print(f'FINISHED: {success}/{total} images saved locally')


if __name__ == '__main__':
    main()
