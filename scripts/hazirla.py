"""ai_navi için hazır veriler (GitHub Actions'ta çalışır, sonuçlar GitHub Pages'te yayımlanır).

Telefon bu dosyaları indirir; ağır işler (EPDK'nın 16 MB'lık listesi, OpenStreetMap sorguları, il il fiyatlar,
mola yerlerinin yapay zekâ değerlendirmesi) telefonda yapılmaz.

Kullanım: python scripts/hazirla.py [sarj] [opet] [akaryakit] [mola] [hepsi]
Her adım bağımsızdır; bir adım başarısız olursa önceki dosya korunur.
"""
from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import os
import re
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
            iller[str(kod)] = {"ad": ad, "ilceler": ilceler,
                               "il": [statistics.median_low(benzin), statistics.median_low(motorin)]}
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


# --- 4) Mola yerleri: tesis / dinlenme alanları + otoyol / ana yol kenarı yeme-içme; yapay zekâ değerlendirmesi ---

def mola_turu(t: dict) -> str:
    if t.get("highway") == "services":
        return "tesis"
    if t.get("highway") == "rest_area":
        return "dinlenme"
    return {"cafe": "kafe", "fast_food": "hizli", "restaurant": "restoran"}.get(t.get("amenity"), "restoran")


# Yapay zekâ yoksa ya da değerlendiremediyse türüne göre puan (yemek, kahve, dinlenme; 0-3)
KURAL = {"tesis": (2, 2, 3), "dinlenme": (0, 0, 2), "restoran": (3, 1, 1), "kafe": (1, 3, 1), "hizli": (2, 1, 1)}

ONEMLI_ETIKETLER = ("name", "brand", "operator", "amenity", "highway", "cuisine", "opening_hours", "toilets",
                    "fuel", "shop", "outdoor_seating", "wheelchair", "description", "drive_through", "takeaway",
                    "playground", "mosque", "charging_station")


def mola(manifest: dict):
    log("Mola yerleri (OpenStreetMap)...")
    yerler = {}
    sorgular = [
        f'[out:json][timeout:600];{TR_ALAN}nwr["highway"~"^(services|rest_area)$"](area.tr);out center tags;',
        # Otoyol / ana yol kenarındaki (300 m) restoran, kafe, hızlı yemek
        f'[out:json][timeout:900];{TR_ALAN}way["highway"~"^(motorway|trunk)$"](area.tr)->.yol;'
        f'nwr(around.yol:300)["amenity"~"^(restaurant|cafe|fast_food)$"]["name"];out center tags;',
    ]
    for i, q in enumerate(sorgular):
        try:
            for e in overpass(q).get("elements", []):
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
                kimlik = f"{e['type'][0]}{e['id']}"
                yerler[kimlik] = {"id": kimlik, "lat": round(m[0], 6), "lon": round(m[1], 6), "tur": tur, "ad": ad,
                                  "etiket": {k: t[k] for k in ONEMLI_ETIKETLER if k in t}}
        except Exception as e:
            if i == 0:
                raise
            log(f"  yol kenarı sorgusu başarısız, yalnız tesisler: {e}")
    if len(yerler) < 200:
        raise RuntimeError(f"beklenenden az mola yeri ({len(yerler)})")
    puanlar = degerlendir(list(yerler.values()))
    satirlar = []
    for y in yerler.values():
        p = puanlar.get(y["id"])
        ye, ka, di = (p["yemek"], p["kahve"], p["dinlenme"]) if p else KURAL[y["tur"]]
        not_ = temiz(p["not"]) if p else ""
        satirlar.append(f"M;{y['id']};{y['lat']};{y['lon']};{y['tur']};{ye};{ka};{di};{temiz(y['ad'])};{not_}")
    yaz("mola.txt", "\n".join(satirlar) + "\n", len(satirlar), manifest)


AI_SISTEM = """Türkiye'deki yol kenarı mola yerlerini (dinlenme tesisi, dinlenme alanı, restoran, kafe, hızlı yemek) OpenStreetMap etiketlerine göre değerlendiriyorsun. Uzun yolda giden bir sürücü için her yere 0-3 arası üç puan ver:
- yemek: düzgün bir yemek molası için uygunluk (restoran / lokanta / tesiste yemek)
- kahve: kısa kahve / çay / atıştırma molası için uygunluk
- dinlenme: tuvalet, oturma, araç park, esneme molası için uygunluk
0 uygun değil, 1 zayıf, 2 iyi, 3 çok iyi. Bilgi azsa türünden makul bir tahmin yap (dinlenme tesisi genelde yemek/kahve/dinlenme için iyidir; dinlenme alanında çoğu zaman yeme-içme yoktur).
not: sürücüye gösterilecek en çok 60 karakterlik kısa Türkçe açıklama (ör. "Restoran, kafe ve tuvalet var", "Büyük tesis, 24 saat açık"). Etiketlerde olmayan bir şeyi kesinmiş gibi yazma.
Her yer için id'yi aynen geri ver."""

AI_SEMA = {
    "type": "object",
    "properties": {
        "degerlendirmeler": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "yemek": {"type": "integer"},
                    "kahve": {"type": "integer"},
                    "dinlenme": {"type": "integer"},
                    "not": {"type": "string"},
                },
                "required": ["id", "yemek", "kahve", "dinlenme", "not"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["degerlendirmeler"],
    "additionalProperties": False,
}


def degerlendir(yerler: list[dict]) -> dict:
    """Yapay zekâ puanları; önbellekte olanlar (aynı etiketler) yeniden sorulmaz. Her çalışmada en çok AI_SINIR yeni yer."""
    ONBELLEK.mkdir(exist_ok=True)
    yol = ONBELLEK / "ai_puan.json"
    onbellek = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}

    def anahtar(y):
        return hashlib.sha1(json.dumps([y["tur"], y["ad"], y["etiket"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

    yeni = [y for y in yerler if onbellek.get(y["id"], {}).get("h") != anahtar(y)]
    # Tesisler önce (yol kenarı yemek-içmeden daha önemli)
    yeni.sort(key=lambda y: {"tesis": 0, "dinlenme": 1}.get(y["tur"], 2))
    sinir = int(os.environ.get("AI_SINIR", "600"))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("  ANTHROPIC_API_KEY yok: yapay zekâ değerlendirmesi atlandı (türüne göre puan)")
        yeni = []
    else:
        log(f"  yapay zekâ: {min(len(yeni), sinir)} / {len(yeni)} yeni yer değerlendirilecek")
        yeni = yeni[:sinir]
    if yeni:
        import anthropic
        client = anthropic.Anthropic()
        for i in range(0, len(yeni), 40):
            parca = yeni[i:i + 40]
            girdi = json.dumps([{"id": y["id"], "tur": y["tur"], "ad": y["ad"], "etiket": y["etiket"]} for y in parca],
                               ensure_ascii=False)
            try:
                r = client.beta.messages.create(
                    model="claude-opus-5-5",
                    max_tokens=16000,
                    system=AI_SISTEM,
                    messages=[{"role": "user", "content": girdi}],
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": AI_SEMA}},
                    # Güvenlik sınıflandırıcısı reddederse sunucu uygun modele geçer
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
            except anthropic.RateLimitError:
                log("  yapay zekâ hız sınırı: kalanlar sonraki çalışmaya")
                break
            except anthropic.APIStatusError as e:
                log(f"  yapay zekâ hatası {e.status_code}: {e.message}")
                break
            except anthropic.APIConnectionError as e:
                log(f"  yapay zekâya bağlanılamadı: {e}")
                break
            if r.stop_reason == "refusal":
                log("  yapay zekâ bu parçayı yanıtlamadı; türüne göre puan")
                continue
            metin = next((b.text for b in r.content if b.type == "text"), "")
            try:
                sonuc = json.loads(metin)["degerlendirmeler"]
            except (ValueError, KeyError):
                log("  yapay zekâ yanıtı okunamadı")
                continue
            harita = {y["id"]: y for y in parca}
            for s in sonuc:
                y = harita.get(s.get("id"))
                if not y:
                    continue
                onbellek[y["id"]] = {"h": anahtar(y), "yemek": max(0, min(3, int(s["yemek"]))),
                                     "kahve": max(0, min(3, int(s["kahve"]))),
                                     "dinlenme": max(0, min(3, int(s["dinlenme"]))), "not": str(s["not"])[:80]}
            log(f"  {i + len(parca)} / {len(yeni)}")
        yol.write_text(json.dumps(onbellek, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    # Yalnızca etiketleri değişmemiş yerlerin puanı geçerli
    guncel = {y["id"]: anahtar(y) for y in yerler}
    return {k: v for k, v in onbellek.items() if guncel.get(k) == v.get("h")}


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
