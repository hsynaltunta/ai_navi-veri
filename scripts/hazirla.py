"""ai_navi için hazır veriler (GitHub Actions'ta çalışır, sonuçlar GitHub Pages'te yayımlanır).

Telefon bu dosyaları indirir; ağır işler (EPDK'nın 16 MB'lık listesi, OpenStreetMap sorguları, il il fiyatlar,
mola yerlerinin puanlanması) telefonda yapılmaz.
Ücretli servis kullanılmaz: puanlar yalnızca OpenStreetMap bilgisinden çıkarılır.

Kullanım: python scripts/hazirla.py [sarj] [opet] [akaryakit] [mola] [hepsi]
Her adım bağımsızdır; bir adım başarısız olursa önceki dosya korunur.
"""
from __future__ import annotations

import gzip
import http.client
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "public" / "veri"
ONBELLEK = KOK / "data"
UA = "ai_navi-veri/1.0 (+https://github.com/hsynaltunta/ai_navi-veri)"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def log(*a):
    print(*a, flush=True)


# --- Ortak ---

def temiz(s: str | None) -> str:
    return (s or "").replace("\n", " ").replace(";", ",").strip()


def norm(s: str) -> str:
    """Uygulamadaki PriceBook.norm ile aynı: küçük harf, Türkçe harfler sade, yalnız harf / rakam"""
    s = s.replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ş", "s"), ("ı", "i"), ("ç", "c"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("i̇", "i")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if ch.isascii() and ch.isalnum())


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding", "") == "gzip":
            data = gzip.decompress(data)
        return data


def overpass(query: str, timeout: int = 900) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode()
    son = None
    for url in OVERPASS:
        for deneme in range(2):
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except Exception as e:  # sunucu dolu / zaman aşımı: biraz bekleyip yeniden, sonra sıradaki ayna
                son = e
                log(f"  Overpass {url}: {e}")
                time.sleep(20)
    raise RuntimeError(f"Overpass yanıt vermedi: {son}")


def merkez(e: dict) -> tuple[float, float] | None:
    if "lat" in e:
        return e["lat"], e["lon"]
    c = e.get("center")
    return (c["lat"], c["lon"]) if c else None


def yaz(ad: str, metin: str, sayi: int, manifest: dict):
    CIKTI.mkdir(parents=True, exist_ok=True)
    (CIKTI / ad).write_text(metin, encoding="utf-8")
    manifest["dosyalar"][ad] = {"zaman": int(time.time() * 1000), "sayi": sayi,
                                "boyut": len(metin.encode("utf-8"))}
    log(f"  {ad}: {sayi} kayıt, {len(metin.encode('utf-8')) // 1024} KB")


# --- 1) Şarj istasyonları: EPDK ---

def epdk_istasyon(rec: dict) -> str | None:
    """Uygulamadaki StationLogic.epdkStation ile aynı kurallar -> önbellek satırı"""
    if rec.get("hizmetSekli") not in (None, "HALKA_ACIK"):
        return None
    try:
        lat = float(str(rec.get("enlem")).replace(",", "."))
        lon = float(str(rec.get("boylam")).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not (35.0 <= lat <= 43.0 and 25.0 <= lon <= 45.0):
        return None
    soketler = rec.get("soketler") or []
    fast = any((s.get("soketTipi") or "").upper() == "DC" or (s.get("soketTuru") or "").upper().startswith("DC")
               or "CHADEMO" in (s.get("soketTuru") or "").upper() for s in soketler)
    ac = any((s.get("soketTipi") or "").upper() == "AC" or (s.get("soketTuru") or "").upper().startswith("AC")
             for s in soketler)
    guc = []
    for s in soketler:
        try:
            g = float(str(s.get("soketGucu")).replace(",", "."))
            if g > 0:
                guc.append(g)
        except (TypeError, ValueError):
            pass
    b = temiz(rec.get("marka"))
    n = temiz(rec.get("sarjIstasyonuAdi"))
    if not n:
        ad = b or "Şarj noktası"
    elif not b or b.lower() in n.lower():
        ad = n
    else:
        ad = f"{b} • {n}"
    kw = str(max(guc)) if guc else ""
    return f"S;C;{lat};{lon};{1 if fast else 0};{1 if (ac or not fast) else 0};{kw};0;{b};{ad}"


def sarj(manifest: dict):
    log("Şarj istasyonları (EPDK)...")
    conn = http.client.HTTPSConnection("apigateway.epdk.gov.tr", timeout=180)
    # Servis yalnızca gövdeli GET kabul ediyor (POST 404)
    conn.request("GET", "/sarjIstasyonlari", body="{}",
                 headers={"Content-Type": "application/json", "Accept-Encoding": "gzip", "User-Agent": UA})
    r = conn.getresponse()
    data = r.read()
    if r.status != 200:
        raise RuntimeError(f"EPDK HTTP {r.status}")
    if (r.getheader("Content-Encoding") or "") == "gzip":
        data = gzip.decompress(data)
    satirlar = [s for s in (epdk_istasyon(x) for x in json.loads(data)["data"]) if s]
    if len(satirlar) < 5000:
        raise RuntimeError(f"beklenenden az istasyon ({len(satirlar)})")
    yaz("sarj.txt", "\n".join(satirlar) + "\n", len(satirlar), manifest)


# --- 2) Akaryakıt fiyatları: Opet, tüm iller (İstanbul 34 Anadolu, 934 Avrupa) ---

def opet(manifest: dict):
    log("Akaryakıt fiyatları (Opet)...")
    iller = {}
    for kod in list(range(1, 82)) + [934]:
        try:
            veri = json.loads(http_get(f"https://api.opet.com.tr/api/fuelprices/prices?ProvinceCode={kod}&IncludeAllProducts=true", 30))
        except Exception as e:
            log(f"  il {kod}: {e}")
            continue
        ilceler, benzin, motorin, ad = {}, [], [], ""
        for d in veri:
            ad = d.get("provinceName") or ad
            b = m = None
            for p in d.get("prices") or []:
                fiyat = p.get("amount") or 0
                if fiyat <= 0:
                    continue
                if p.get("productCode") == "A100":
                    b = fiyat
                elif m is None and (p.get("productName") or "").startswith("Motorin"):
                    m = fiyat
            if b and m:
                ilceler[norm(d.get("districtName") or "")] = [b, m]
                benzin.append(b)
                motorin.append(m)
        if benzin:
            # ai_pilot'taki yöntem (Ownership.parseOpet): ilçe fiyatlarının ortancası, sıralı listenin [n/2] elemanı
            iller[str(kod)] = {"ad": ad, "ilceler": ilceler,
                               "il": [sorted(benzin)[len(benzin) // 2], sorted(motorin)[len(motorin) // 2]]}
        time.sleep(0.3)
    if len(iller) < 60:
        raise RuntimeError(f"beklenenden az il ({len(iller)})")
    metin = json.dumps({"kaynak": "Opet", "iller": iller}, ensure_ascii=False, separators=(",", ":"))
    yaz("opet.json", metin, len(iller), manifest)


# --- 3) Akaryakıt istasyonları: OpenStreetMap, tüm Türkiye ---

TR_ALAN = 'area["ISO3166-1"="TR"][admin_level=2]->.tr;'


def akaryakit(manifest: dict):
    log("Akaryakıt istasyonları (OpenStreetMap)...")
    d = overpass(f'[out:json][timeout:600];{TR_ALAN}nwr["amenity"="fuel"](area.tr);out center tags;')
    satirlar = []
    for e in d.get("elements", []):
        m = merkez(e)
        if not m:
            continue
        t = e.get("tags", {})
        marka = temiz(t.get("brand") or t.get("operator"))
        ad = temiz(t.get("name") or marka) or "Akaryakıt istasyonu"
        lpg = 1 if t.get("fuel:lpg") not in (None, "no", "0") else 0
        satirlar.append(f"S;F;{m[0]};{m[1]};0;0;;{lpg};{marka};{ad}")
    if len(satirlar) < 5000:
        raise RuntimeError(f"beklenenden az istasyon ({len(satirlar)})")
    yaz("akaryakit.txt", "\n".join(satirlar) + "\n", len(satirlar), manifest)


# --- 4) Mola yerleri: tesis / dinlenme alanları + otoyol / ana yol kenarı yeme-içme; ücretsiz kural puanı ---

def mola_turu(t: dict) -> str:
    if t.get("highway") == "services":
        return "tesis"
    if t.get("highway") == "rest_area":
        return "dinlenme"
    return {"cafe": "kafe", "fast_food": "hizli", "restaurant": "restoran"}.get(t.get("amenity"), "restoran")


class Izgara:
    """Yakınlık araması için ~1 km'lik hücreler (enlem/boylam x100)"""

    def __init__(self):
        self.h: dict[tuple[int, int], list] = {}

    def ekle(self, la: float, lo: float, deger):
        self.h.setdefault((int(la * 100), int(lo * 100)), []).append((la, lo, deger))

    def yakindakiler(self, la: float, lo: float, metre: float = 300):
        """[metre] içindeki değerler (enlemde 1° ~111 km, boylamda cos(40°) ile ~85 km)"""
        dla, dlo = metre / 111_000, metre / 85_000
        ci, cj = int(la * 100), int(lo * 100)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for (pa, po, d) in self.h.get((ci + di, cj + dj), ()):
                    if ((la - pa) / dla) ** 2 + ((lo - po) / dlo) ** 2 <= 1:
                        yield d


def ozellikler(tur: str, t: dict, cevre: list[str]) -> dict:
    """Yerin kendi etiketleri + 300 m çevresindeki yerler (restoran, kafe, hızlı yemek, akaryakıt, tuvalet)"""
    c = set(cevre)
    kendi = {"restoran": "restaurant", "kafe": "cafe", "hizli": "fast_food"}.get(tur)
    if kendi:
        c.add(kendi)
    if t.get("toilets") == "yes":
        c.add("toilets")
    if t.get("fuel") == "yes" or any(k.startswith("fuel:") for k in t):
        c.add("fuel")
    return {
        "restoran": "restaurant" in c, "kafe": "cafe" in c, "hizli": "fast_food" in c,
        "akaryakit": "fuel" in c, "tuvalet": "toilets" in c,
        "acik24": (t.get("opening_hours") or "").strip() == "24/7",
        "mutfak": (t.get("cuisine") or "").split(";")[0].strip(),
    }


MUTFAK = {"kebab": "kebap", "turkish": "Türk mutfağı", "regional": "yöresel", "fish": "balık", "seafood": "deniz ürünleri",
          "chicken": "tavuk", "burger": "burger", "pizza": "pizza", "coffee_shop": "kahve", "breakfast": "kahvaltı",
          "pide": "pide", "steak_house": "et", "grill": "ızgara", "meat": "et", "soup": "çorba", "dessert": "tatlı",
          "sandwich": "sandviç", "doner": "döner", "lahmacun": "lahmacun", "homestyle": "ev yemekleri"}


def puanla(tur: str, o: dict) -> tuple[int, int, int, str]:
    """(yemek, kahve, dinlenme 0-3, kısa açıklama); ücretli servis yok, yalnız OpenStreetMap bilgisi"""
    yemek = 3 if o["restoran"] else 2 if o["hizli"] else (1 if tur == "tesis" else 0)
    kahve = 3 if o["kafe"] else 2 if (o["restoran"] or o["hizli"]) else 1 if (o["akaryakit"] or tur == "tesis") else 0
    dinlenme = {"tesis": 2, "dinlenme": 2}.get(tur, 1)
    if o["tuvalet"]:
        dinlenme += 1
    if tur == "tesis" and (o["restoran"] or o["kafe"]):
        dinlenme += 1
    if o["acik24"]:
        yemek, kahve = (min(3, yemek + 1) if yemek else 0), (min(3, kahve + 1) if kahve else 0)
    parca = [ad for ad, var in (("restoran", o["restoran"]), ("kafe", o["kafe"]), ("hızlı yemek", o["hizli"]),
                                ("akaryakıt", o["akaryakit"]), ("tuvalet", o["tuvalet"])) if var]
    metin = ", ".join(parca).capitalize() + (" var" if parca else "")
    if o["mutfak"] and o["restoran"]:
        metin += f" ({MUTFAK.get(o['mutfak'].lower(), o['mutfak'].replace('_', ' '))})"
    if o["acik24"]:
        metin += ("; " if metin else "") + "24 saat açık"
    return min(3, yemek), min(3, kahve), min(3, dinlenme), metin[:80]


def mola(manifest: dict):
    log("Mola yerleri (OpenStreetMap)...")
    tesisler = overpass(f'[out:json][timeout:600];{TR_ALAN}nwr["highway"~"^(services|rest_area)$"](area.tr);out center tags;')
    yeme = overpass(f'[out:json][timeout:900];{TR_ALAN}nwr["amenity"~"^(restaurant|cafe|fast_food)$"](area.tr);out center tags;')
    diger = overpass(f'[out:json][timeout:900];{TR_ALAN}nwr["amenity"~"^(fuel|toilets)$"](area.tr);out center;')
    # Çevre ızgarası: yeme-içme, akaryakıt, tuvalet
    cevre = Izgara()
    for e in yeme.get("elements", []) + diger.get("elements", []):
        m = merkez(e)
        if m:
            cevre.ekle(m[0], m[1], (e.get("tags") or {}).get("amenity", ""))
    # Otoyol / ana yol kenarı (300 m): yollar ayrı alınır, yakınlık burada süzülür (tek "around" sorgusu zaman aşımına uğruyor)
    yollar = Izgara()
    try:
        for w in overpass(f'[out:json][timeout:900];{TR_ALAN}way["highway"~"^(motorway|trunk)$"](area.tr);out geom;').get("elements", []):
            g = w.get("geometry") or []
            for a, b in zip(g, g[1:]):
                adim = max(1, int(((a["lat"] - b["lat"]) ** 2 + (a["lon"] - b["lon"]) ** 2) ** 0.5 / 0.002))
                for k in range(adim + 1):  # ~200 m aralıkla yol noktaları
                    yollar.ekle(a["lat"] + (b["lat"] - a["lat"]) * k / adim, a["lon"] + (b["lon"] - a["lon"]) * k / adim, 1)
    except Exception as e:
        log(f"  yollar alınamadı, yalnız tesisler: {e}")
    adaylar = list(tesisler.get("elements", []))
    adaylar += [e for e in yeme.get("elements", []) if (e.get("tags") or {}).get("name") and (m := merkez(e))
                and next(yollar.yakindakiler(m[0], m[1]), None) is not None]
    satirlar = []
    for e in adaylar:
        m = merkez(e)
        if not m:
            continue
        t = e.get("tags", {})
        tur = mola_turu(t)
        ad = temiz(t.get("name:tr") or t.get("name") or t.get("brand"))
        if not ad:
            ad = "Dinlenme tesisi" if tur == "tesis" else "Dinlenme alanı" if tur == "dinlenme" else ""
        if not ad:
            continue
        cevredekiler = list(cevre.yakindakiler(m[0], m[1]))
        ye, ka, di, not_ = puanla(tur, ozellikler(tur, t, cevredekiler))
        satirlar.append(f"M;{e['type'][0]}{e['id']};{round(m[0], 6)};{round(m[1], 6)};{tur};{ye};{ka};{di};{ad};{temiz(not_)}")
    satirlar = list(dict.fromkeys(satirlar))
    if len(satirlar) < 200:
        raise RuntimeError(f"beklenenden az mola yeri ({len(satirlar)})")
    log(f"  {len(tesisler.get('elements', []))} tesis / dinlenme alanı, {len(satirlar)} mola yeri")
    yaz("mola.txt", "\n".join(satirlar) + "\n", len(satirlar), manifest)


# --- Ana ---

ADIMLAR = {"sarj": sarj, "opet": opet, "akaryakit": akaryakit, "mola": mola}


def main():
    istenen = sys.argv[1:] or ["hepsi"]
    if "hepsi" in istenen:
        istenen = list(ADIMLAR)
    yol = CIKTI / "manifest.json"
    manifest = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {"surum": 1, "dosyalar": {}}
    hata = 0
    for ad in istenen:
        try:
            ADIMLAR[ad](manifest)
        except Exception as e:
            hata += 1
            log(f"!! {ad} başarısız (önceki dosya korunuyor): {e}")
    manifest["guncelleme"] = int(time.time() * 1000)
    CIKTI.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Bitti ({len(istenen) - hata}/{len(istenen)} adım başarılı)")


if __name__ == "__main__":
    main()
