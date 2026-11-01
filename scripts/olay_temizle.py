"""Süresi dolan yol bildirimlerini (başlığı "olay: " ile başlayan açık kayıtlar) kapatır. GitHub Actions'ta saatte bir.

Süreler uygulamadaki ReportType ile aynı (dakika). Gövdesi okunamayan ya da 24 saati geçen kayıt da kapatılır.
Yetki: iş akışının kendi geçici GITHUB_TOKEN'ı (yalnız bu depo, yalnız kayıtlar).
"""
import json
import os
import time
import urllib.request
from datetime import datetime

SURE = {"kaza": 120, "polis": 60, "trafik": 60, "calisma": 24 * 60, "tehlike": 120, "arac": 90}
REPO = os.environ.get("GITHUB_REPOSITORY", "hsynaltunta/ai_navi-veri")


def istek(yontem, url, govde=None):
    req = urllib.request.Request(url, method=yontem, data=json.dumps(govde).encode() if govde else None, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json",
        "User-Agent": "ai_navi-veri"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def main():
    simdi = time.time()
    kapatilan = 0
    sayfa = 1
    while True:
        kayitlar = istek("GET", f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100&page={sayfa}")
        if not kayitlar:
            break
        for k in kayitlar:
            if "pull_request" in k or not k["title"].startswith("olay: "):
                continue
            yas_dk = (simdi - datetime.fromisoformat(k["created_at"].replace("Z", "+00:00")).timestamp()) / 60
            try:
                sure = SURE.get(json.loads(k.get("body") or "{}").get("tur"), 0)
            except ValueError:
                sure = 0
            if yas_dk > sure or yas_dk > 24 * 60:
                istek("PATCH", f"https://api.github.com/repos/{REPO}/issues/{k['number']}",
                      {"state": "closed", "state_reason": "completed"})
                kapatilan += 1
        sayfa += 1
    print(f"Süresi dolan {kapatilan} bildirim kapatıldı")


if __name__ == "__main__":
    main()
