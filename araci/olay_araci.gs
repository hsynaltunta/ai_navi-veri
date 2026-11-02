/**
 * ai_navi yol bildirimi aracısı (Google Apps Script web uygulaması, ücretsiz).
 *
 * Uygulama bildirimi buraya gönderir ({"tur","lat","lon","zaman"}); betik denetler ve GitHub'da
 * hsynaltunta/ai_navi-veri deposunda "olay: ..." kaydı açar. GitHub anahtarı yalnızca bu betiğin
 * Komut dosyası özelliklerinde (GITHUB_TOKEN) durur; uygulamada ve herkese açık dosyalarda yoktur.
 *
 * Denetimler: tür listede mi, konum Türkiye'de mi, aynı türde 200 m içinde son 10 dakikada bildirim var mı
 * (varsa yeni kayıt açılmaz), dakikada en çok 20 istek (kötüye kullanıma karşı).
 *
 * Oylar ({"islem":"evet"|"yok","no":kayıt}): "hâlâ orada" süreyi yeniler, iki "yok artık" kaydı kapatır.
 * Öneri ({"islem":"oneri","metin","bilgi"}): "öneri: ..." kaydı açar (saatte en çok 30).
 */

var DEPO = 'hsynaltunta/ai_navi-veri';
var TURLER = {
  kaza: 'Kaza', polis: 'Trafik denetimi', trafik: 'Trafik sıkışıklığı',
  calisma: 'Yol çalışması', tehlike: 'Yolda tehlike', arac: 'Yolda duran araç'
};
var DAKIKADA_EN_COK = 20;
/** Bu kadar "yok artık" oyu alan bildirim kapanır */
var YOK_ESIGI = 2;

function doGet() {
  return yanit({ ok: true, mesaj: 'ai_navi olay aracı çalışıyor', surum: 3 });
}

function doPost(e) {
  var v;
  try {
    v = JSON.parse(e.postData.contents);
  } catch (err) {
    return yanit({ ok: false, hata: 'geçersiz istek' });
  }
  if (v.islem === 'evet' || v.islem === 'yok') return oy(v.islem, Number(v.no));
  if (v.islem === 'oneri') return oneri(String(v.metin || ''), String(v.bilgi || ''));
  var tur = String(v.tur || '');
  var lat = Number(v.lat), lon = Number(v.lon);
  if (!TURLER[tur]) return yanit({ ok: false, hata: 'bilinmeyen tür' });
  if (!(lat >= 35 && lat <= 43 && lon >= 25 && lon <= 45)) return yanit({ ok: false, hata: 'konum Türkiye dışında' });

  var kilit = LockService.getScriptLock();
  kilit.waitLock(10000);
  try {
    var onbellek = CacheService.getScriptCache();
    // Dakikalık sınır
    var dakika = 'dk_' + Math.floor(Date.now() / 60000);
    var sayi = Number(onbellek.get(dakika) || 0);
    if (sayi >= DAKIKADA_EN_COK) return yanit({ ok: false, hata: 'çok fazla bildirim, biraz sonra deneyin' });
    onbellek.put(dakika, String(sayi + 1), 120);

    // Aynı yerde aynı tür: yeni kayıt açılmaz (10 dakika)
    var son = JSON.parse(onbellek.get('son') || '[]').filter(function (s) { return Date.now() - s.z < 600000; });
    for (var i = 0; i < son.length; i++) {
      if (son[i].t === tur && mesafeM(son[i].a, son[i].o, lat, lon) < 200) return yanit({ ok: true, ayni: true });
    }

    var anahtar = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
    if (!anahtar) return yanit({ ok: false, hata: 'aracı ayarlanmamış' });
    var govde = JSON.stringify({
      tur: tur, lat: Math.round(lat * 100000) / 100000, lon: Math.round(lon * 100000) / 100000, zaman: Date.now()
    });
    var c = UrlFetchApp.fetch('https://api.github.com/repos/' + DEPO + '/issues', {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + anahtar, Accept: 'application/vnd.github+json' },
      payload: JSON.stringify({ title: 'olay: ' + TURLER[tur], body: govde }),
      muteHttpExceptions: true
    });
    if (c.getResponseCode() >= 300) return yanit({ ok: false, hata: 'GitHub ' + c.getResponseCode() });

    son.push({ t: tur, a: lat, o: lon, z: Date.now() });
    onbellek.put('son', JSON.stringify(son.slice(-200)), 900);
    return yanit({ ok: true });
  } finally {
    kilit.releaseLock();
  }
}

/**
 * "Hâlâ orada" (evet): bildirimin gövdesindeki zaman yenilenir, süresi baştan başlar.
 * "Yok artık" (yok): oy sayısı artar; YOK_ESIGI'ne ulaşınca kayıt kapanır ve konumu silinir.
 * Yalnız açık "olay: " kayıtlarına oy verilir; dakikalık sınır bildirimlerle ortaktır.
 */
function oy(islem, no) {
  if (!(no > 0)) return yanit({ ok: false, hata: 'geçersiz kayıt' });
  var anahtar = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!anahtar) return yanit({ ok: false, hata: 'aracı ayarlanmamış' });
  var kilit = LockService.getScriptLock();
  kilit.waitLock(10000);
  try {
    var onbellek = CacheService.getScriptCache();
    var dakika = 'dk_' + Math.floor(Date.now() / 60000);
    var sayi = Number(onbellek.get(dakika) || 0);
    if (sayi >= DAKIKADA_EN_COK) return yanit({ ok: false, hata: 'çok fazla istek, biraz sonra deneyin' });
    onbellek.put(dakika, String(sayi + 1), 120);

    var url = 'https://api.github.com/repos/' + DEPO + '/issues/' + no;
    var basliklar = { Authorization: 'Bearer ' + anahtar, Accept: 'application/vnd.github+json' };
    var c = UrlFetchApp.fetch(url, { headers: basliklar, muteHttpExceptions: true });
    if (c.getResponseCode() !== 200) return yanit({ ok: false, hata: 'kayıt bulunamadı' });
    var kayit = JSON.parse(c.getContentText());
    if (kayit.state !== 'open' || String(kayit.title).indexOf('olay: ') !== 0) return yanit({ ok: false, hata: 'kayıt açık değil' });
    var g;
    try { g = JSON.parse(kayit.body || '{}'); } catch (err) { return yanit({ ok: false, hata: 'kayıt okunamadı' }); }

    var guncel;
    if (islem === 'evet') {
      g.zaman = Date.now();
      g.onay = Number(g.onay || 0) + 1;
      guncel = { body: JSON.stringify(g) };
    } else {
      g.yok = Number(g.yok || 0) + 1;
      if (g.yok >= YOK_ESIGI) {
        guncel = { state: 'closed', state_reason: 'not_planned', body: JSON.stringify({ tur: g.tur, silindi: true, yok: g.yok }) };
      } else {
        guncel = { body: JSON.stringify(g) };
      }
    }
    var p = UrlFetchApp.fetch(url, {
      method: 'patch', contentType: 'application/json', headers: basliklar,
      payload: JSON.stringify(guncel), muteHttpExceptions: true
    });
    if (p.getResponseCode() >= 300) return yanit({ ok: false, hata: 'GitHub ' + p.getResponseCode() });
    return yanit({ ok: true });
  } finally {
    kilit.releaseLock();
  }
}

/** Geliştiriciye öneri: herkese açık depoda "öneri: ..." kaydı (konum / kimlik yok) */
function oneri(metin, bilgi) {
  metin = metin.trim();
  if (metin.length < 3) return yanit({ ok: false, hata: 'öneri boş' });
  if (metin.length > 4000) metin = metin.substring(0, 4000);
  bilgi = bilgi.substring(0, 600);
  var anahtar = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!anahtar) return yanit({ ok: false, hata: 'aracı ayarlanmamış' });
  var kilit = LockService.getScriptLock();
  kilit.waitLock(10000);
  try {
    var onbellek = CacheService.getScriptCache();
    var saat = 'oneri_' + Math.floor(Date.now() / 3600000);
    var sayi = Number(onbellek.get(saat) || 0);
    if (sayi >= 30) return yanit({ ok: false, hata: 'çok fazla öneri, biraz sonra deneyin' });
    onbellek.put(saat, String(sayi + 1), 4000);
    // @ ile kişi anma (GitHub bildirimi) engellenir
    var temiz = function (t) { return t.replace(/@/g, '@​'); };
    var baslik = metin.replace(/\s+/g, ' ');
    if (baslik.length > 60) baslik = baslik.substring(0, 57) + '…';
    var govde = temiz(metin) + '\n\n---\n<pre>' + temiz(bilgi).replace(/</g, '&lt;') + '</pre>';
    var c = UrlFetchApp.fetch('https://api.github.com/repos/' + DEPO + '/issues', {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + anahtar, Accept: 'application/vnd.github+json' },
      payload: JSON.stringify({ title: 'öneri: ' + temiz(baslik), body: govde }),
      muteHttpExceptions: true
    });
    if (c.getResponseCode() >= 300) return yanit({ ok: false, hata: 'GitHub ' + c.getResponseCode() });
    return yanit({ ok: true, no: JSON.parse(c.getContentText()).number });
  } finally {
    kilit.releaseLock();
  }
}

function mesafeM(a1, o1, a2, o2) {
  var r = Math.PI / 180, R = 6371000;
  var da = (a2 - a1) * r, d0 = (o2 - o1) * r;
  var h = Math.sin(da / 2) * Math.sin(da / 2) + Math.cos(a1 * r) * Math.cos(a2 * r) * Math.sin(d0 / 2) * Math.sin(d0 / 2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

function yanit(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
