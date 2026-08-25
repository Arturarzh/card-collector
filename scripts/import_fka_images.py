#!/usr/bin/env python3
"""Import public Football Kit Archive kit images into local assets.

Reads the OL history and season pages, discovers individual kit pages,
and downloads each page's og:image locally. No screenshots are used.
"""
import re, json, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://www.footballkitarchive.com'
HISTORY=BASE+'/olympique-lyonnais-kits-t7006/'
OUT=Path('assets/kits'); DATA=Path('data/fka-images.json')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; OL-Kit-Vault/1.0; +https://github.com/Arturarzh/card-collector)'})

def get(url):
    r=S.get(url,timeout=30); r.raise_for_status(); return r.text

def season(text):
    m=re.search(r'(?:19|20)\d{2}-(?:\d{2}|\d{4})',text); return m.group(0) if m else None

def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-') or 'kit'

def discover():
    soup=BeautifulSoup(get(HISTORY),'html.parser'); season_pages=set(); kit_pages=set()
    for a in soup.find_all('a',href=True):
        u=urljoin(BASE,a['href']).rstrip('/')+'/'
        if 'olympique-lyonnais' not in u or not season((a.get_text(' ',strip=True)+' '+u)): continue
        if re.search(r'/olympique-lyonnais-kits-(?:19|20)\d{2}-\d{2}-t7006/?$',u): season_pages.add(u)
        if re.search(r'/olympique-lyonnais-[^/]+-kit-\d+/?$',u): kit_pages.add(u)
    # Every season page exposes hidden variants behind "Show all".
    for u in sorted(season_pages):
        try:
            ss=BeautifulSoup(get(u),'html.parser')
            for a in ss.find_all('a',href=True):
                v=urljoin(BASE,a['href']).rstrip('/')+'/'
                if 'olympique-lyonnais' in v and re.search(r'-kit-\d+/?$',v): kit_pages.add(v)
        except Exception as e: print('season error',u,e)
    return sorted(kit_pages)

def download(url):
    soup=BeautifulSoup(get(url),'html.parser'); title=soup.title.get_text(' ',strip=True) if soup.title else url
    seas=season(title+' '+url) or 'unknown'
    og=soup.find('meta',attrs={'property':'og:image'}) or soup.find('meta',attrs={'name':'twitter:image'})
    if not og or not og.get('content'): return None
    img=urljoin(url,og['content']); host=urlparse(img).netloc
    if 'footballkitarchive.com' not in host: return None
    r=S.get(img,timeout=30); r.raise_for_status(); data=r.content
    if len(data)<1000: return None
    out=OUT/seas; out.mkdir(parents=True,exist_ok=True)
    filename=slug(re.sub(r'\s*[-|].*$','',title))+'-'+hashlib.sha1(url.encode()).hexdigest()[:10]+'.jpg'
    path=out/filename; path.write_bytes(data)
    return {'season':seas,'title':title,'source':url,'image':str(path).replace('\\','/'),'sha1':hashlib.sha1(data).hexdigest(),'bytes':len(data)}

def main():
    OUT.mkdir(parents=True,exist_ok=True); urls=discover(); print('discovered',len(urls),'kit pages')
    records=[]
    for i,u in enumerate(urls,1):
        try:
            rec=download(u)
            if rec: records.append(rec); print(f'[{i}/{len(urls)}] OK {rec["title"]}')
            else: print(f'[{i}/{len(urls)}] NO IMAGE {u}')
        except Exception as e: print(f'[{i}/{len(urls)}] ERROR {u}: {e}')
        time.sleep(.15)
    DATA.parent.mkdir(parents=True,exist_ok=True); DATA.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('saved',len(records),'images')
if __name__=='__main__': main()
