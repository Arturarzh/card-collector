#!/usr/bin/env python3
"""Import public Football Kit Archive kit images into local assets.

The collector is intentionally limited to Olympique Lyonnais men's kit pages.
It reads the public FKA history/season pages, discovers individual kit pages,
and downloads each page's og:image locally. It does not use screenshots.
"""
import os, re, json, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = 'https://www.footballkitarchive.com'
HISTORY = BASE + '/olympique-lyonnais-kits-t7006/'
OUT = Path('assets/kits')
DATA = Path('data/fka-images.json')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; OL-Kit-Vault/1.0; +https://github.com/Arturarzh/card-collector)'})


def get(url):
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def season_from_text(text):
    m = re.search(r'(19|20)\d{2}-(?:\d{2}|\d{4})', text)
    return m.group(0) if m else None


def slug(s):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s or 'kit'


def discover():
    html = get(HISTORY)
    soup = BeautifulSoup(html, 'html.parser')
    urls = set()
    # The history page exposes every season and a large portion of individual kits.
    for a in soup.find_all('a', href=True):
        href = urljoin(BASE, a['href'])
        txt = ' '.join(a.stripped_strings)
        if 'olympique-lyonnais' in href and season_from_text(txt + ' ' + href):
            if re.search(r'/olympique-lyonnais-[^/]+-kit[-/]', href) or re.search(r'/[^/]*-kit-\d+/?$', href):
                urls.add(href.rstrip('/') + '/')
            elif re.search(r'/olympique-lyonnais-kits-(?:19|20)\d{2}-', href):
                urls.add(href.rstrip('/') + '/')
    # Crawl season pages to reveal hidden "Show all" kits.
    season_pages = sorted(u for u in urls if '/kits-' in u and u.rstrip('/').endswith(tuple(f'{y}-{str((y+1)%100).zfill(2)}' for y in range(1950, 2027))))
    for u in season_pages:
        try:
            s = BeautifulSoup(get(u), 'html.parser')
            for a in s.find_all('a', href=True):
                href = urljoin(BASE, a['href'])
                txt = ' '.join(a.stripped_strings)
                if 'olympique-lyonnais' in href and season_from_text(txt + ' ' + href) and re.search(r'-kit[-/]\d+/?$', href):
                    urls.add(href.rstrip('/') + '/')
        except Exception as e:
            print('season error', u, e)
    # Keep only individual OL kit pages, not the archive index itself.
    return sorted(u for u in urls if re.search(r'-kit[-/]\d+/?$', u))


def download_page(url):
    html = get(url)
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else url
    season = season_from_text(title + ' ' + url) or 'unknown'
    og = soup.find('meta', attrs={'property':'og:image'}) or soup.find('meta', attrs={'name':'twitter:image'})
    if not og or not og.get('content'):
        return None
    img_url = urljoin(url, og['content'])
    # Do not follow unrelated external images.
    host = urlparse(img_url).netloc
    if 'footballkitarchive.com' not in host and 'cdn.' not in host:
        return None
    data = SESSION.get(img_url, timeout=30).content
    if not data or len(data) < 1000:
        return None
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    name = slug(re.sub(r'\s*[-|].*$', '', title)) + '-' + h + '.jpg'
    outdir = OUT / season
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / name
    path.write_bytes(data)
    return {'season':season,'title':title,'source':url,'image':str(path).replace('\\','/'),'sha1':hashlib.sha1(data).hexdigest(),'bytes':len(data)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = discover()
    print('discovered', len(urls), 'individual kit pages')
    records=[]
    for i,u in enumerate(urls,1):
        try:
            rec=download_page(u)
            if rec:
                records.append(rec)
                print(f'[{i}/{len(urls)}] OK {rec["title"]}')
            else:
                print(f'[{i}/{len(urls)}] NO IMAGE {u}')
        except Exception as e:
            print(f'[{i}/{len(urls)}] ERROR {u}: {e}')
        time.sleep(0.15)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('saved',len(records),'images')

if __name__ == '__main__': main()
