# ai_navi-veri

ai_navi navigasyon uygulamasının indirdiği hazır veriler (GitHub Pages: https://hsynaltunta.github.io/ai_navi-veri/).
`scripts/hazirla.py` GitHub Actions'ta çalışır: şarj istasyonları (EPDK) ve akaryakıt fiyatları (Opet) her gün;
akaryakıt istasyonları ve mola yerleri (OpenStreetMap) ile mola yerlerinin yapay zekâ değerlendirmesi (Claude) haftada bir.

Yapay zekâ değerlendirmesi için depo ayarlarında `ANTHROPIC_API_KEY` gizli değişkeni gerekir; yoksa mola yerleri
türlerine göre puanlanır. Değerlendirmeler `data/ai_puan.json`'da saklanır, yalnızca yeni / değişen yerler sorulur.

OpenStreetMap verileri © OpenStreetMap katkıcıları, ODbL lisansı.
