# ai_navi-veri

ai_navi navigasyon uygulamasının indirdiği hazır veriler (GitHub Pages: https://hsynaltunta.github.io/ai_navi-veri/).
`scripts/hazirla.py` GitHub Actions'ta çalışır: şarj istasyonları (EPDK) ve akaryakıt fiyatları (Opet) her gün;
akaryakıt istasyonları ve mola yerleri (OpenStreetMap) haftada bir.

Ücretli servis kullanılmaz. Mola yerlerinin yemek / kahve / dinlenme puanları (0-3) ve kısa açıklaması yalnızca
OpenStreetMap bilgisinden çıkarılır: yerin kendi etiketleri (24 saat açık, mutfak, tuvalet) ve 300 m çevresindeki
restoran, kafe, hızlı yemek, akaryakıt istasyonu ve tuvaletler.

OpenStreetMap verileri © OpenStreetMap katkıcıları, ODbL lisansı.
