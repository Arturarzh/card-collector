import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from playwright.async_api import async_playwright

BASE = "https://www.footballkitarchive.com"
HISTORY = f"{BASE}/fr/olympique-lyonnais-maillots-t7006/"
OUT = Path("assets/kits")
DATA = Path("data/fka-kits.json")
OUT.mkdir(parents=True, exist_ok=True)
DATA.parent.mkdir(parents=True, exist_ok=True)

TEAM_WORDS = ("olympique-lyonnais", "olympique lyonnais")
EXCLUDE = ("training", "travel", "track", "rain", "bench", "staff", "polo", "sweatshirt", "hoodie", "jacket", "vest", "anthem")

def slug(s):
    return re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-") or "kit"

def season_from(text):
    m = re.search(r"(19|20)\d{2}-\d{2}", text)
    return m.group(0) if m else None

def should_keep(label):
    low = label.lower()
    return any(w in low for w in TEAM_WORDS) and not any(x in low for x in EXCLUDE)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000}, user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36")
        await page.goto(HISTORY, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2500)
        links = await page.locator("a").evaluate_all("els => els.map(a => ({href:a.href, text:(a.innerText||a.textContent||'').trim()}))")
        season_pages, seen = [], set()
        for a in links:
            season = season_from(a["text"])
            href = a["href"]
            if season and href.startswith(BASE) and season not in seen and "olympique-lyonnais" in href and "kits" in href:
                seen.add(season); season_pages.append((season, href))
        for y in range(1950, 2027):
            season = f"{y}-{str((y+1)%100).zfill(2)}"
            href = f"{BASE}/olympique-lyonnais-kits-{season}-t7006/"
            if season not in seen: season_pages.append((season, href))

        results = []
        for season, season_url in sorted(season_pages, reverse=True):
            try:
                await page.goto(season_url, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(900)
                anchors = await page.locator("a").evaluate_all("els => els.map(a => ({href:a.href, text:(a.innerText||a.textContent||'').trim(), title:a.title||''}))")
                kits, kit_seen = [], set()
                for a in anchors:
                    label = (a["text"] or a["title"] or "").strip(); href = a["href"]
                    if not href.startswith(BASE) or href in kit_seen or not should_keep(label): continue
                    if "-kits-" in href and href.rstrip('/').endswith("t7006"): continue
                    kit_seen.add(href); kits.append((label, href))
                for label, href in kits:
                    try:
                        await page.goto(href, wait_until="domcontentloaded", timeout=120000)
                        await page.wait_for_timeout(350)
                        og = await page.locator('meta[property="og:image"]').get_attribute("content")
                        if not og: og = await page.locator('meta[name="twitter:image"]').get_attribute("content")
                        if not og: continue
                        og = urljoin(BASE, og)
                        safe = slug(label.replace("Olympique Lyonnais", "OL"))
                        ext = os.path.splitext(urlparse(og).path)[1] or ".jpg"
                        dest = OUT / f"{season}-{safe}{ext}"
                        if not dest.exists():
                            r = requests.get(og, headers={"User-Agent":"Mozilla/5.0"}, timeout=60)
                            r.raise_for_status(); dest.write_bytes(r.content)
                        results.append({"id": f"{season}-{safe}", "season": season, "name": label, "page": href, "image": str(dest).replace(os.sep, "/")})
                    except Exception as e:
                        print("IMAGE ERROR", season, label, e)
            except Exception as e:
                print("SEASON ERROR", season, season_url, e)
        DATA.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Imported {len(results)} OL kit images")
        await browser.close()

if __name__ == "__main__": asyncio.run(main())
