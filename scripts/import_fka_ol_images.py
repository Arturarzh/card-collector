#!/usr/bin/env python3
"""Populate every OL archive reference with a visible Google Images thumbnail.

The importer uses data/ol-archive.json as the authoritative list of references,
then searches Google Images and stores the first usable thumbnail locally. The
site reads the generated data/fka-kits.json, so it never needs to load an
archive page just to display a photo.
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
MANIFEST = Path('data/fka-kits.json')
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
    return [
        img.get('src') for img in soup.find_all('img')
        if (img.get('src') or '').startswith('https://encrypted-tbn0.gstatic.com/images')
    ]


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

    for season, kit_types in archive.items():
        for kit_type in kit_types:
            count += 1
            kit_id = f'{season}-{kit_type}'
            name = f'OL {season} · {kit_type}'
            query = f'Olympique Lyonnais {season} {kit_type} maillot football shirt jersey'
            dest = OUT / (slug(kit_id) + '.jpg')
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
                'id': kit_id,
                'season': season,
                'name': name,
                'type': kit_type,
                'image': str(dest).replace('\\', '/') if ok else '',
                'source': 'Google Images',
                'query': query,
                'page': 'https://www.google.com/search?tbm=isch&q=' + quote(query)
            })
            print(f'[{count}/{total}] {"OK" if ok else "NO IMAGE"} {name}')
            time.sleep(0.35)

    MANIFEST.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    success = sum(1 for x in records if x['image'])
    print(f'FINISHED: {success}/{total} images saved locally')


if __name__ == '__main__':
    main()
