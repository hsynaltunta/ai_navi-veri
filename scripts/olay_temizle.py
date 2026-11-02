"""Süresi dolan yol bildirimlerini (başlığı "olay: " ile başlayan açık kayıtlar) kapatır. GitHub Actions'ta saatte bir.

Süreler uygulamadaki ReportType ile aynı (dakika); "hâlâ orada" onayı gövdedeki zamanı yenilediği için süre
max(oluşturma, gövdedeki zaman)'dan sayılır. Gövdesi okunamayan ya da 24 saati geçen kayıt da kapatılır.
Gizlilik: kapatılan kaydın gövdesindeki konum silinir (yalnız tür kalır); önceden kapatılmış ama konumu duran
kayıtlar da temizlenir.
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


def kayitlar(durum, en_cok_sayfa=10):
    for sayfa in range(1, en_cok_sayfa + 1):
        liste = istek("GET", f"https://api.github.com/repos/{REPO}/issues?state={durum}&per_page=100&page={sayfa}")
        if not liste:
            return
        for k in liste:
            if "pull_request" not in k and k["title"].startswith("olay: "):
                yield k


def govde(k) -> dict:
    try:
        return json.loads(k.get("body") or "{}")
    except ValueError:
        return {}


def konumsuz(g: dict) -> dict:
    return {"tur": g.get("tur"), "silindi": True}


def main():
    simdi = time.time()
    kapatilan = temizlenen = 0
    for k in list(kayitlar("open")):
        g = govde(k)
        olusma = datetime.fromisoformat(k["created_at"].replace("Z", "+00:00")).timestamp()
        zaman = g.get("zaman") / 1000 if isinstance(g.get("zaman"), (int, float)) else olusma
        son = max(olusma, min(zaman, simdi))  # onayla yenilenen zaman
        sure = SURE.get(g.get("tur"), 0)
        if (simdi - son) / 60 > sure or (simdi - olusma) / 60 > 3 * 24 * 60:
            istek("PATCH", f"https://api.github.com/repos/{REPO}/issues/{k['number']}",
                  {"state": "closed", "state_reason": "completed", "body": json.dumps(konumsuz(g))})
            kapatilan += 1
    # Önceden kapatılmış ama konumu hâlâ gövdede duran kayıtlar
    for k in kayitlar("closed", 3):
        g = govde(k)
        if "lat" in g or "lon" in g:
            istek("PATCH", f"https://api.github.com/repos/{REPO}/issues/{k['number']}", {"body": json.dumps(konumsuz(g))})
            temizlenen += 1
    print(f"Süresi dolan {kapatilan} bildirim kapatıldı, {temizlenen} kapalı kaydın konumu silindi")


if __name__ == "__main__":
    main()
