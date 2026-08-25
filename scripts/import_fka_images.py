#!/usr/bin/env python3
"""Build the local OL kit image archive from Football Kit Archive references.

Priority:
1) Individual Football Kit Archive kit page -> og:image/twitter:image.
2) If FKA blocks the request, use Bing Images only to locate the same public FKA
   image/CDN asset, keeping the FKA kit page as the canonical reference.

Every downloaded file is validated as an actual image, hashed, and recorded.
"""
import io, json, re, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus
import requests
from bs4 import BeautifulSoup
from PIL import Image

BASE = 'https://www.footballkitarchive.com'
HISTORY = BASE + '/olympique-lyonnais-kits-t7006/'
OUT = Path('assets/kits')
DATA = Path('data/fka-images.json')
REPORT = Path('data/fka-image-report.json')

S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
})


def fetch(url, timeout=30):
    r = S.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def season(text):
    m = re.search(r'((?:19|20)\d{2}-(?:\d{2}|\d{4}))', text)
    return m.group(1) if m else 'unknown'


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-') or 'kit'


def kit_url(u):
    return re.search(r'olympique-lyonnais-[^/]+-kit-\d+/?$', u) is not None


def discover():
    """Discover every OL kit page linked by FKA's history and season pages."""
    season_pages, kit_pages = set(), set()
    r = fetch(HISTORY)
    soup = BeautifulSoup(r.text, 'html.parser')
    links = [urljoin(BASE, a['href']).rstrip('/') + '/' for a in soup.find_all('a', href=True)]
    for u in links:
        txt = u
        if 'olympique-lyonnais' not in u or not season(txt):
            continue
        if re.search(r'/olympique-lyonnais-kits-(?:19|20)\d{2}-\d{2}-t7006/?$', u):
            season_pages.add(u)
        if kit_url(u):
            kit_pages.add(u)

    for i, u in enumerate(sorted(season_pages), 1):
        try:
            ss = BeautifulSoup(fetch(u).text, 'html.parser')
            for a in ss.find_all('a', href=True):
                v = urljoin(BASE, a['href']).rstrip('/') + '/'
                if 'olympique-lyonnais' in v and kit_url(v):
                    kit_pages.add(v)
        except Exception as e:
            print('SEASON_ERROR', i, u, repr(e))
        time.sleep(.08)
    return sorted(kit_pages)


def page_title(html, fallback):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.title.get_text(' ', strip=True) if soup.title else fallback


def fka_image_from_page(url, html):
    soup = BeautifulSoup(html, 'html.parser')
    for attrs in ({'property': 'og:image'}, {'name': 'twitter:image'}):
        node = soup.find('meta', attrs=attrs)
        if node and node.get('content'):
            img = urljoin(url, node['content'])
            if 'footballkitarchive.com' in urlparse(img).netloc:
                return img
    # Some FKA pages expose the CDN image in JSON/script data.
    patterns = [
        r'https://cdn\.footballkitarchive\.com/[^\"\']+',
        r'https:\\/\\/cdn\.footballkitarchive\.com\\/[^\"\']+'
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(0).replace('\\/', '/')
    return None


def bing_candidates(query):
    """Return image URLs from Bing search HTML, prioritising FKA/CDN results."""
    url = 'https://www.bing.com/images/search?q=' + quote_plus(query) + '&form=HDRSC2'
    r = fetch(url, 25)
    soup = BeautifulSoup(r.text, 'html.parser')
    out = []
    for a in soup.select('a.iusc'):
        m = a.get('m')
        if not m:
            continue
        try:
            obj = json.loads(m)
            for key in ('turl', 'murl'):
                u = obj.get(key)
                if u and u not in out:
                    out.append(u)
        except Exception:
            continue
    # FKA/CDN first, then other image results.
    out.sort(key=lambda u: (0 if 'footballkitarchive.com' in urlparse(u).netloc else 1))
    return out[:30]


def valid_image(data):
    if len(data) < 5000:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            return {'format': im.format, 'width': im.width, 'height': im.height}
    except Exception:
        return None


def download_image(url):
    r = fetch(url, 30)
    info = valid_image(r.content)
    if not info:
        return None
    return r.content, info


def import_one(kit_url_value):
    html = None
    try:
        html = fetch(kit_url_value).text
    except Exception as e:
        print('FKA_PAGE_ERROR', kit_url_value, repr(e))

    title = page_title(html, kit_url_value) if html else kit_url_value
    seas = season(title + ' ' + kit_url_value)
    candidates = []
    if html:
        img = fka_image_from_page(kit_url_value, html)
        if img:
            candidates.append(('fka-page', img))

    # If FKA page is blocked or image is unusable, locate the same FKA asset via Bing.
    if not candidates:
        q = 'site:footballkitarchive.com ' + title.replace(' - Football Kit Archive', '')
        try:
            candidates.extend(('bing', u) for u in bing_candidates(q))
        except Exception as e:
            print('BING_ERROR', title, repr(e))

    tried = set()
    for source, img_url in candidates:
        if img_url in tried:
            continue
        tried.add(img_url)
        try:
            result = download_image(img_url)
            if not result:
                continue
            data, info = result
            sha1 = hashlib.sha1(data).hexdigest()
            outdir = OUT / seas
            outdir.mkdir(parents=True, exist_ok=True)
            filename = slug(re.sub(r'\s*[-|].*$', '', title)) + '-' + sha1[:10] + '.jpg'
            path = outdir / filename
            path.write_bytes(data)
            return {
                'season': seas, 'title': title, 'source': kit_url_value,
                'image': str(path).replace('\\', '/'), 'image_source': img_url,
                'image_lookup': source, 'sha1': sha1, 'bytes': len(data), **info
            }
        except Exception as e:
            print('IMAGE_ERROR', title, img_url, repr(e))
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = discover()
    print('DISCOVERED_KIT_PAGES', len(urls))
    records, missing = [], []
    for i, u in enumerate(urls, 1):
        rec = import_one(u)
        if rec:
            records.append(rec)
            print(f'[{i}/{len(urls)}] OK {rec["title"]} -> {rec["image"]}')
        else:
            missing.append(u)
            print(f'[{i}/{len(urls)}] MISSING {u}')
        time.sleep(.12)

    # Deduplicate identical image bytes while keeping every kit reference.
    seen = {}
    for rec in records:
        if rec['sha1'] in seen:
            rec['duplicate_of'] = seen[rec['sha1']]
        else:
            seen[rec['sha1']] = rec['image']

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {
        'canonical_source': HISTORY,
        'discovered_kit_pages': len(urls),
        'images_imported': len(records),
        'images_missing': len(missing),
        'missing_pages': missing,
        'verified_image_files': sum(1 for r in records if r.get('width') and r.get('height')),
        'duplicates': sum(1 for r in records if r.get('duplicate_of'))
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('FINAL_REPORT', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
