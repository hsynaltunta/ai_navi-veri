# Yol bildirimi aracısı — kurulum

Uygulamadaki kullanıcılar kaza, polis çevirmesi gibi bildirimleri bu aracıya gönderir; aracı denetleyip GitHub'da
kayıt açar. GitHub anahtarı yalnızca Google'daki betiğin ayarında durur. Ücretsizdir.

## 1. GitHub anahtarı (yalnız bu depo, yalnız kayıt izni)

1. https://github.com/settings/personal-access-tokens/new adresini aç (Fine-grained token).
2. **Token name:** `ai_navi olay aracı`
3. **Expiration:** 1 yıl (ya da istediğin süre; bitince yenisini oluşturup 2. adımdaki ayarı güncellersin).
4. **Repository access:** "Only select repositories" → **ai_navi-veri**.
5. **Permissions → Repository permissions → Issues:** "Read and write". Başka izin verme.
6. **Generate token** → çıkan anahtarı kopyala (bir daha gösterilmez).

## 2. Google Apps Script

1. https://script.google.com → **Yeni proje**; adı: `ai_navi olay aracı`.
2. Açılan `Kod.gs` içeriğini sil, bu klasördeki `olay_araci.gs` dosyasının tamamını yapıştır, kaydet.
3. Soldaki **⚙ Proje ayarları** → en altta **Komut dosyası özellikleri** → **Komut dosyası özelliği ekle**:
   - Özellik: `GITHUB_TOKEN`
   - Değer: 1. adımda kopyaladığın anahtar
   - **Komut dosyası özelliklerini kaydet**.
4. Sağ üstte **Dağıt → Yeni dağıtım** → türü (⚙) **Web uygulaması**:
   - Açıklama: `ai_navi olay aracı`
   - Şu kullanıcı olarak yürüt: **Ben**
   - Erişimi olanlar: **Herkes**
   - **Dağıt** → izin isterse hesabını seç → "Gelişmiş" → "... (güvenli değil) sayfasına git" → **İzin ver**.
5. Çıkan **Web uygulaması URL'sini** kopyala (`https://script.google.com/macros/s/.../exec`). Bu adres gizli değildir.

## 3. Uygulamaya bağlama

Web uygulaması adresini Claude'a ver; depo ayarına (`OLAY_URL` değişkeni) eklenir ve uygulamalar bir sonraki
açılışta bu adresi kullanır.

Betiği sonradan değiştirirsen: **Dağıt → Dağıtımları yönet → kalem → Sürüm: Yeni sürüm → Dağıt** (adres değişmez).
