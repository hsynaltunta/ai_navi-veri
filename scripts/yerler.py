"""Türkiye yer deposu: OpenStreetMap'ten adı olan işletme / yerler, kapı numaralı adresler ve bina adları.

GitHub Actions'ta haftada bir çalışır (yerler.yml): Geofabrik turkey-latest.osm.pbf indirilir, pyosmium ile okunur,
0,5° x 0,5° hücrelere bölünür (out/y_<enlem*2>_<boylam*2>.txt). Telefon yalnız bulunduğu ve çevresindeki hücreleri
indirir, aramayı kendisi yapar. Dosyalar GitHub Releases'e ("yerler" sürümü) yüklenir; depo geçmişi büyümez.

Satır biçimi (sekmeyle ayrılmış):  ad  enlem  boylam  tür  adres
Lisans: © OpenStreetMap katkıcıları, ODbL.
"""
import json
import math
import os
import sys
from collections import defaultdict

import osmium

OUT = sys.argv[2] if len(sys.argv) > 2 else "out"

# Tür adları (ilk eşleşen etiket); listede yoksa etiket değeri yazılır
TUR = {
    "amenity": {"restaurant": "Restoran", "cafe": "Kafe", "fast_food": "Fast food", "pharmacy": "Eczane", "hospital": "Hastane",
                "clinic": "Klinik", "doctors": "Doktor", "dentist": "Diş hekimi", "school": "Okul", "university": "Üniversite",
                "college": "Kolej", "kindergarten": "Anaokulu", "bank": "Banka", "atm": "ATM", "fuel": "Akaryakıt",
                "charging_station": "Şarj istasyonu", "place_of_worship": "İbadethane", "police": "Polis", "post_office": "Postane",
                "townhall": "Belediye", "courthouse": "Adliye", "library": "Kütüphane", "cinema": "Sinema", "theatre": "Tiyatro",
                "parking": "Otopark", "bar": "Bar", "pub": "Pub", "car_wash": "Oto yıkama", "veterinary": "Veteriner",
                "marketplace": "Pazar yeri", "bus_station": "Otogar", "ferry_terminal": "İskele"},
    "shop": {"supermarket": "Market", "convenience": "Bakkal / market", "bakery": "Fırın", "car_repair": "Oto tamir",
             "car": "Oto galeri", "car_parts": "Oto yedek parça", "tyres": "Lastikçi", "clothes": "Giyim", "hairdresser": "Kuaför",
             "butcher": "Kasap", "hardware": "Hırdavat", "furniture": "Mobilya", "electronics": "Elektronik",
             "mobile_phone": "Telefoncu", "optician": "Optik", "jewelry": "Kuyumcu", "florist": "Çiçekçi", "mall": "AVM"},
    "office": {}, "craft": {}, "tourism": {"hotel": "Otel", "museum": "Müze", "attraction": "Gezi yeri", "guest_house": "Pansiyon"},
    "leisure": {"park": "Park", "sports_centre": "Spor merkezi", "stadium": "Stadyum", "fitness_centre": "Spor salonu"},
    "healthcare": {}, "historic": {}, "aeroway": {"aerodrome": "Havalimanı"}, "railway": {"station": "İstasyon"},
    "public_transport": {"station": "İstasyon"}, "industrial": {}, "landuse": {"industrial": "Sanayi", "commercial": "Ticari alan"},
    "place": {"neighbourhood": "Mahalle", "suburb": "Semt", "quarter": "Mahalle", "village": "Köy", "town": "İlçe",
              "city": "Şehir", "hamlet": "Mezra"},
    "building": {},
}
SKIP_PLACE = {"locality", "isolated_dwelling", "farm", "plot", "square"}


def tur(tags):
    for k, names in TUR.items():
        v = tags.get(k)
        if not v or v == "no":
            continue
        if k == "place" and v in SKIP_PLACE:
            continue
        if k == "building" and v in ("yes",):
            return "Bina"
        return names.get(v, v.replace("_", " "))
    return None


def adres(tags):
    street = tags.get("addr:street", "")
    no = tags.get("addr:housenumber", "")
    parts = []
    if street:
        parts.append(f"{street} No:{no}" if no else street)
    elif no:
        parts.append(f"No:{no}")
    for k in ("addr:neighbourhood", "addr:suburb", "addr:district", "addr:city"):
        v = tags.get(k)
        if v and v not in parts:
            parts.append(v)
    return ", ".join(parts)


def temiz(s):
    return s.replace("\t", " ").replace("\n", " ").strip()


class Yerler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.cells = defaultdict(list)
        self.n = 0

    def add(self, tags, lat, lon):
        name = tags.get("name:tr") or tags.get("name") or ""
        t = tur(tags)
        a = adres(tags)
        no = tags.get("addr:housenumber")
        if not name:
            # Adsız ama kapı numaralı adres: "Sokak No:5"
            if no and tags.get("addr:street"):
                name = f"{tags['addr:street']} No:{no}"
                t = t or "Adres"
            else:
                return
        elif not t and not no:
            return  # adı var ama ne yer ne adres (ör. yol, nehir)
        key = f"{math.floor(lat * 2)}_{math.floor(lon * 2)}"
        self.cells[key].append(f"{temiz(name)}\t{lat:.5f}\t{lon:.5f}\t{temiz(t or '')}\t{temiz(a)}")
        self.n += 1

    def node(self, n):
        if n.tags and n.location.valid():
            self.add(dict(n.tags), n.location.lat, n.location.lon)

    def way(self, w):
        if not w.tags:
            return
        tags = dict(w.tags)
        if "highway" in tags and "addr:housenumber" not in tags and "name" in tags and tur(tags) is None:
            return
        lat = lon = 0.0
        k = 0
        try:
            for nd in w.nodes:
                if nd.location.valid():
                    lat += nd.location.lat
                    lon += nd.location.lon
                    k += 1
        except osmium.InvalidLocationError:
            return
        if k:
            self.add(tags, lat / k, lon / k)


def main():
    pbf = sys.argv[1]
    h = Yerler()
    h.apply_file(pbf, locations=True, idx="flex_mem")
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for key, lines in sorted(h.cells.items()):
        lines = sorted(set(lines))
        path = os.path.join(OUT, f"y_{key}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        manifest[key] = {"n": len(lines), "kb": os.path.getsize(path) // 1024}
    with open(os.path.join(OUT, "yerler.json"), "w", encoding="utf-8") as f:
        json.dump({"hucre": 0.5, "kayit": h.n, "hucreler": manifest}, f, ensure_ascii=False)
    big = sorted(manifest.items(), key=lambda kv: -kv[1]["kb"])[:8]
    total = sum(v["kb"] for v in manifest.values())
    print(f"{h.n} kayıt, {len(manifest)} hücre, toplam {total // 1024} MB; en büyükler: " +
          ", ".join(f"{k}={v['kb'] // 1024} MB/{v['n']}" for k, v in big))


if __name__ == "__main__":
    main()
