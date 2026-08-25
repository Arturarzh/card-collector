#!/usr/bin/env python3
import io,json,re,time,hashlib
from pathlib import Path
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup
from PIL import Image

ARCHIVE=Path('data/ol-archive.json'); OUT=Path('assets/kits'); DATA=Path('data/fka-images.json'); REPORT=Path('data/fka-image-report.json')
FKA='https://www.footballkitarchive.com/olympique-lyonnais-kits-t7006/'
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0','Accept-Language':'fr-FR,fr;q=0.9,en;q=0.8'})

def valid(b):
    if len(b)<3000:return None
    try:
        with Image.open(io.BytesIO(b)) as im: im.verify()
        with Image.open(io.BytesIO(b)) as im:return {'format':im.format,'width':im.width,'height':im.height}
    except:return None

def search(q):
    r=S.get('https://www.bing.com/images/search?q='+quote_plus(q)+'&form=HDRSC2',timeout=25); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser'); out=[]
    for a in soup.select('a.iusc'):
        try:o=json.loads(a.get('m','{}'))
        except:continue
        for k in ('turl','murl'):
            u=o.get(k)
            if u and u not in out:out.append(u)
    return out[:50]

def slug(s):return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-') or 'kit'

def main():
    archive=json.loads(ARCHIVE.read_text(encoding='utf8')); refs=[{'season':s,'type':t,'title':f'Olympique Lyonnais {s} {t}'} for s,ts in archive.items() for t in ts]
    OUT.mkdir(parents=True,exist_ok=True); records=[]; missing=[]; seen={}
    for i,ref in enumerate(refs,1):
        urls=[]
        for q in [f'"{ref["title"]}" football kit',f'"Olympique Lyonnais" "{ref["season"]}" "{ref["type"]}" maillot']:
            try:urls += search(q)
            except Exception as e:print('SEARCH_ERROR',repr(e))
            if len(urls)>=60:break
        rec=None
        for u in dict.fromkeys(urls):
            try:
                rr=S.get(u,timeout=25); info=valid(rr.content)
                if not info:continue
                sha=hashlib.sha1(rr.content).hexdigest(); ext={'PNG':'png','WEBP':'webp','JPEG':'jpg'}.get(info['format'],'jpg'); p=OUT/ref['season']/(slug(ref['type'])+'-'+sha[:10]+'.'+ext); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(rr.content)
                rec={**ref,'image':str(p).replace('\\','/'),'image_source':u,'sha1':sha,**info,'canonical_source':FKA}
                if sha in seen:rec['duplicate_of']=seen[sha]
                else:seen[sha]=rec['image']
                break
            except Exception:continue
        if rec:records.append(rec); print(f'[{i}/{len(refs)}] OK {ref["title"]}')
        else:missing.append(ref); print(f'[{i}/{len(refs)}] MISSING {ref["title"]}')
        time.sleep(.1)
    DATA.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    report={'canonical_catalogue':FKA,'catalogue_references':len(refs),'images_imported':len(records),'images_missing':len(missing),'verified_image_files':sum(bool(r.get('width') and r.get('height')) for r in records),'duplicates':sum(bool(r.get('duplicate_of')) for r in records),'missing_references':missing}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(report,ensure_ascii=False))
    if missing:raise SystemExit(2)
main()
