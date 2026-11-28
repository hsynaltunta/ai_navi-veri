"""Şarj fiyatları: işletmecilerin kendi sitelerinde yayımladığı tarifeler.

Şarj Hizmeti Yönetmeliği işletmecileri fiyatlarını internet sitelerinde yayımlamakla yükümlü kılar; burada yalnızca
bu resmî sayfalar okunur (günde bir istek, kimliği belli User-Agent). Sayfası okunamayan işletmecinin son geçerli
fiyatı 45 güne kadar korunur; daha eskiyse listeden çıkar (uygulama o işletmecide "tahmini" fiyat gösterir).

Çıktı satırı: ad;ac;dc;kontrol;ac_en_cok;dc_en_cok;kaynak (TL/kWh, KDV dahil; aralık yoksa en çok boş)
"""
from __future__ import annotations

import datetime
import html
import re

N = r"(\d{1,2}[,.]\d{1,2})"
ARA = r"(?:\s*[-–]\s*" + N + r")?"

# ad (EPDK marka adıyla eşleşir), kaynak sayfa, AC deseni, DC deseni (grup 1 en az, grup 2 varsa en çok)
ISLETMECILER = [
    ("ZES", "https://zes.net/tr/fiyatlandirma",
     r"\bAC\s*" + N + r"\s*₺\s*/\s*kWh", r"DC-2\s*" + N + r"\s*₺\s*/\s*kWh(?:\s*-\s*" + N + r")?"),
    ("Trugo", "https://trugo.com.tr/price",
     r"AC cihazlar için 1 kWh ücreti\s*" + N + r"(?:\s*TL)?" + ARA, r"DC cihazlar için 1 kWh ücreti\s*" + N + r"(?:\s*TL)?" + ARA),
    ("WAT Mobilite", "https://www.watmobilite.com/cozumler/kamusal-alanlar",
     r"AC Tarife AC:\s*" + N + ARA, r"DC Tarife DC:\s*" + N + ARA),
    ("Otopriz", "https://otopriz.com.tr/uyelik-ve-tarifeler",
     r"AC Type 2 Soketler FİYAT/BİRİM\s*" + N + ARA, r"DC CCS Soketler FİYAT/BİRİM\s*" + N + ARA),
    ("En Yakıt", "https://www.enyakit.com.tr/ucretlendirme",
     None, r"\s" + N + r"\s*TL/kWh fiyatla"),
    ("Ovolt", "https://ovolt.com.tr/tarifeler",
     r"AC Tarife\s*(?:\(\s*TL/kWh\s*\))?\s*" + N + ARA, r"DC Tarife\s*(?:\(\s*TL/kWh\s*\))?\s*" + N + ARA),
    ("OnCharge", "https://oncharge.com.tr/fiyatlar",
     r"AC şarj\s*" + N + r"\s*TL/kWh", r"DC hızlı şarj\s*" + N + r"\s*TL/kWh"),
    ("Beefull", "https://beefull.com/tarifeler/elektrikli-arac-tarifesi/",
     r"AC SOKET TARİFESİ Fiyat / Birim\s*" + N, r"DC SOKET TARİFESİ Fiyat / Birim\s*" + N),
    ("Aksa Şarj", "https://aksasarj.com.tr/ucretler",
     r"Ücretler AC\s*" + N + ARA, r"TL / kWh DC\s*" + N + ARA),
    ("D-Charge", "https://dcharge.com.tr/tarifeler",
     r"Tüm AC Soketler\s*" + N, r"Tüm DC Soketler\s*" + N),
    ("MKS Şarj", "https://mkssarj.com/tarife",
     r"AC Tip 2 Soketler\s*" + N, r"DC CCS\s*" + N + r"\s*TL/kWh"),
    ("Charging Vehicles CV", "https://cv-charging.com/tr/arac-sarj-tarifeleri",
     r"AC Araç Şarj Cihazı\s*\d+kW\s*" + N, r"DC Araç Şarj Cihazı\s*\d+kW\s*" + N),
    ("PowerŞarj", "https://powersarj.com/fiyatlandirma/",
     r"AC Şarj Tarifesi Tip 2 Soketler\s*₺\s*" + N, r"DC Şarj Tarifesi CCS/SAE Soketler\s*₺\s*" + N),
    ("Neva Şarj", "https://nevasarj.com/sayfalar/istasyonlarimiz/arac-sarj-ac-dc-kwh-fiyat-tarifeleri.html",
     r"AC Soketler\s*" + N + r"\s*TL/kWh", r"DC Soketler\s*" + N + r"\s*TL/kWh"),
    ("Asplus", "https://asplussarj.com/fiyatlar",
     r"AC Tip [\d./]+ KW Soket\s*" + N, r"DC Tip \d+ KW Soket\s*" + N),
    ("Varr", "https://varr.com.tr",
     r"Tüm AC Soketler\s*" + N, r"Tüm DC Soketler\s*;?\s*" + N),
    ("i-Şarj", "https://www.isarj.com/tarifeler/",
     r"FİYAT /BİRİM AC\s*" + N, r"FİYAT /BİRİM DC\s*" + N),
    ("Şarjon", "https://sarjon.com.tr/fiyatlar/",
     r"Fiyatlar AC\s*" + N, r"DC-1\s*" + N + r"\s*TL / kWh(?:\s*DC-2\s*" + N + r")?"),
    ("ADZE", "https://www.adze.com/tr/fiyat-tarifesi",
     r"AC şarj\s*" + N + r"\s*TL/kWh", r"DC hızlı şarj\s*\([\d\s-]+kW\)\s*ise\s*" + N),
    ("Lumicle", "https://lumicle.com.tr/",
     r"AC Soket Tarifesi:\s*" + N, r"DC Soket Tarifesi:?\s*" + N),
    ("Efish", "https://www.efish.com.tr/tr/fiyatlandirma/",
     r"FİYATLANDIRMA AC\s*" + N, r"TL/kWh DC\s*" + N),
    ("MyCharge", "https://mycharge.com.tr/tarifeler/",
     r"AC\s*[–-]\s*Hızlı Şarj\s*" + N, r"DC\s*[–-]\s*Ultra Hızlı Şarj\s*" + N),
    ("Obişarj", "https://obisarj.com/tarifeler/",
     r"AC Soket Tarifesi\s*₺\s*" + N, r"DC Soket Tarifesi\s*₺\s*" + N),
    ("ENH Şarj", "https://enhsarj.com",
     r"Tüm AC soketler için geçerlidir\s*" + N, r"Tüm DC soketler için geçerlidir\s*" + N),
    ("Sepaş", "https://sepascharge.com/sarj-ucretleri",
     r"\bFiyat\s*" + N + r"\s*TL / kWh", r"\bFiyat\s*\d+[,.]\d+\s*TL / kWh\s*" + N),
    ("Otojet", "https://www.oto-jet.com.tr/fiyatlarimiz.html",
     r"AC Tarife\s*₺\s*" + N, r"DC Tarife\s*₺\s*" + N),
    ("Tunçmatik", "https://tuncmatikcharge.com/fiyatlar/",
     r"AC Soket Tarifesi\s*" + N, r"DC Soket Tarifesi\s*" + N),
    ("Toger", "https://toger.co/",
     r"AC şarj ile[^₺]{0,160}₺\s*" + N, r"DC şarj ile[^₺]{0,160}₺\s*" + N),
    ("Elaris", "https://elaris.com.tr/elaris-tarife/",
     r"AC Socket\s*" + N + r"\s*₺\s*AC-22", r"DC Socket\s*" + N + r"\s*₺"),
    ("EV-Bee", "https://www.ev-bee.com/sabit-sarj-istasyonlari-fiyat-listesi",
     r"AC Soket Fiyat / Birim\s*" + N, r"DC Soket Fiyat / Birim\s*" + N),
    ("GIO EV", "https://gioev.com/fiyatlandirma",
     r"AC Normal şarj Standart tarife\s*" + N, r"DC Hızlı şarj Fiyat aralığı\s*" + N + ARA),
    ("Rst ChargePoint", "https://rstchargepoint.com/",
     r"AC Şarj \(22kW\)\s*" + N, r"DC Hızlı Şarj \(\d+kW\)\s*" + N),
    ("Tora Şarj", "https://torasarj.com/fiyatlar/",
     r"AC Soket Tarifesi\s*" + N, r"DC Soket Tarifesi\s*" + N),
    ("Volti", "https://volti.com/elektrikli-arac-sarj-fiyatlari/",
     r"AC Şarj Ücreti:\s*" + N, r"DC Şarj Ücreti:\s*[\d-]+ kwh:\s*" + N + r"\s*TL / kWh(?:\s*\d+ kwh:\s*" + N + r")?"),
]

EN_AZ, EN_COK = 4.0, 30.0
SAKLA_GUN = 45


def metin(sayfa: str) -> str:
    """HTML -> tek satır düz metin"""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", sayfa, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("​", "")
    return re.sub(r"\s+", " ", t)


def sayi(s: str | None) -> float | None:
    return float(s.replace(",", ".")) if s else None


def oku(desen: str | None, t: str) -> tuple[float | None, float | None]:
    """Desenden (en az, en çok); bulunamaz ya da akla yatkın değilse (None, None)"""
    if not desen:
        return None, None
    m = re.search(desen, t)
    if not m:
        return None, None
    a = sayi(m.group(1))
    b = sayi(m.group(2)) if m.lastindex and m.lastindex >= 2 else None
    if a is None or not EN_AZ <= a <= EN_COK or (b is not None and not a <= b <= EN_COK):
        return None, None
    return a, (b if b is not None and b > a else None)


def satir(ad, ac, dc, kontrol, ac2, dc2, url) -> str:
    f = lambda v: "" if v is None else f"{v:.2f}"
    return ";".join([ad, f(ac), f(dc), kontrol, f(ac2), f(dc2), url])


def eski_liste(metin_: str) -> dict[str, str]:
    """Önceki dosya: ad -> satır"""
    return {s.split(";")[0]: s for s in metin_.splitlines() if s.count(";") >= 6}


def topla(getir, onceki: str, bugun: datetime.date | None = None, log=print) -> list[str]:
    """getir(url) -> html. Okunamayan işletmecide önceki satır (en çok 45 günlük) korunur."""
    bugun = bugun or datetime.date.today()
    eski = eski_liste(onceki)
    cikti = []
    for ad, url, ac_d, dc_d in ISLETMECILER:
        try:
            t = metin(getir(url))
            ac, ac2 = oku(ac_d, t)
            dc, dc2 = oku(dc_d, t)
            if dc is None and (ac is None or ac_d is not None and dc_d is not None):
                raise ValueError("fiyat bulunamadı")
            cikti.append(satir(ad, ac, dc, bugun.strftime("%d.%m.%Y"), ac2, dc2, url))
            log(f"  {ad}: AC {ac}{'-' + str(ac2) if ac2 else ''}  DC {dc}{'-' + str(dc2) if dc2 else ''}")
        except Exception as e:
            s = eski.get(ad)
            gun = None
            if s:
                try:
                    gun = (bugun - datetime.datetime.strptime(s.split(";")[3], "%d.%m.%Y").date()).days
                except ValueError:
                    pass
            if gun is not None and gun <= SAKLA_GUN:
                cikti.append(s)
                log(f"  {ad}: okunamadı ({e}); {gun} günlük fiyat korunuyor")
            else:
                log(f"  {ad}: okunamadı ({e}); listeden çıktı")
    return cikti
