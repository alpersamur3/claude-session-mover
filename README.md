# Claude Sohbet Taşıyıcı (claude-session-mover)

Claude masaüstü uygulamasındaki sohbetleri (session'ları) **bir hesaptan diğerine**
taşımanı/görünür kılmanı sağlayan küçük bir araç. İki sürüm içerir:

| Dosya | Tür | Açıklama |
|-------|-----|----------|
| [`csm.py`](csm.py) | Terminal (CLI) | Soru-cevap akışıyla hızlı taşıma |
| [`csmui.py`](csmui.py) | Grafik arayüz (Tkinter) | Liste, önizleme, boyut karşılaştırması, günlük |

> ⚠️ **Resmî değildir.** Claude'un yerel veri dosyalarıyla çalışır. Kullanım kendi
> sorumluluğunuzdadır. İşlemden önce uygulamayı kapatın; araç yalnızca **kopyalama**
> yapar, orijinal kaynak kaydı yerinde kalır.

---

## Sorun: "Sohbetim diğer hesapta kaldı, bu hesapta görünmüyor"

Claude masaüstü uygulaması, sohbet **listeleme kayıtlarını hesap bazında** ayrı
klasörlerde tutar:

```
<base>\<hesap-id>\<workspace-id>\local_<uuid>.json
```

Uygulama yalnızca **o an giriş yapılı hesabın** klasörünü okur. Başka bir hesapta
açılmış bir sohbet bu yüzden listede görünmez — oysa sohbet **silinmemiştir**.

Önemli ayrım:

- **Sohbet metni (transkript)** `~/.claude/projects\...\<cliSessionId>.jsonl` altında,
  **ortaktır ve hesaba bağlı değildir.**
- Hesaba bağlı olan tek şey **listeleme kaydı** (`local_*.json`).

Bu araç sadece o küçük listeleme kaydını hedef hesaba kopyalar; sohbetin kendisi
zaten yerinde durur.

Kayıt dosyasının iki kilit alanı:

- `sessionId` → `local_<uuid>` (dosya adıyla **aynıdır**)
- `cliSessionId` → asıl transkript `.jsonl` dosyasını işaret eder

---

## Kurulum / Gereksinim

- **Python 3.8+** (gerçek kurulum; Microsoft Store/sandbox Python **önerilmez**, bkz.
  [Sorun Giderme](#sorun-giderme)).
- GUI için **tkinter** (python.org kurulumlarında hazır gelir).

Bağımlılık yok; yalnızca standart kütüphane kullanır.

---

## Kullanım

Windows'ta **`py` launcher** ile çalıştırmak en güvenlisidir (gerçek Python'a gider,
Store kısayoluna takılmaz):

### Grafik arayüz (önerilen)
```powershell
py csmui.py
```

### Terminal
```powershell
py csm.py
```

### Adımlar
1. **Claude masaüstü uygulamasını tamamen kapatın** (sistem tepsisinden de çıkın).
2. Aracı çalıştırın.
3. **Kaynak hesabı** seçin → sohbetler listelenir.
4. Taşımak istediğiniz sohbet(ler)i seçin.
5. **Hedef hesabı** seçin (kaynak listede çıkmaz).
6. Taşıyın. Çakışma varsa boyutları görüp **üzerine yaz / atla** kararını verin.
7. Claude uygulamasını yeniden açın; sohbet artık hedef hesapta görünür.
   (GUI'de tekrar görmek için **🔄 Yenile**.)

---

## Çakışma ve "üzerine yazma"

Hedef hesapta aynı sohbet **zaten varsa** araç sessizce atlamaz; uyarır ve
karşılaştırma gösterir. "Aynı sohbet" şu durumda tespit edilir:

- aynı `cliSessionId` **veya**
- aynı `sessionId` (= dosya adı).

> Aynı dosya adı **farklı** bir sohbeti gösterebilir (örn. eski hesapta 2.4 MB'lik
> gerçek sohbet vs. mevcut hesapta 835 B'lik bir "stub"). Bu yüzden yalnızca dosya
> adına bakıp körlemesine üzerine yazmak yanlıştır — araç bu yüzden **boyutları
> gösterir** ve onay ister. Örnekteki gibi stub'ı gerçek sohbetle değiştirmek tam da
> istenen sonuçtur.

GUI'de üzerine yazma penceresi şunları yan yana gösterir: sohbet boyutu, kayıt
boyutu, son tarih ve `cliSessionId`. Birden fazla çakışma için "kalanlara da uygula"
seçeneği vardır.

---

## Güvenlik / Geri alma

- Araç kaynak kaydı **kopyalar**; orijinal yerinde kalır.
- **Üzerine yazma**, hedefteki mevcut kaydı değiştirir. Geri almak için günlükte
  yazan hedef dosya yolundan eski içeriği geri koymanız gerekir; emin değilseniz
  önce o dosyanın bir yedeğini alın.
- Yalnızca listeleme kaydı (`local_*.json`) taşınır; transkript dosyalarına
  dokunulmaz.

---

## Nasıl çalışır (teknik)

- Olası tüm depo (base) konumları taranır ve **gerçek yola (`realpath`) çözülür**:
  - `%APPDATA%\Claude\claude-code-sessions`
  - `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code-sessions`
    (MSIX/Store paketli kurulum)
- Yazma işlemi, fiziksel olarak benzersiz **tüm depolara aynalanır** — böylece
  uygulama hangisini okursa okusun sohbet görünür.
- MSIX kurulumda `%APPDATA%\Claude` aslında paket konteynerine giden bir
  **symlink**'tir; araç bunu çözerek doğrudan gerçek konuma yazar.

---

## Sorun Giderme

**"Session klasörü bulunamadı" / hiçbir depo görünmüyor**
Büyük olasılıkla aracı **Microsoft Store / sandbox Python** ile çalıştırıyorsunuz; o
yorumlayıcı MSIX symlink'ini başka bir paketin konteynerine takip edemez. Çözüm:
gerçek Python ile çalıştırın:
```powershell
py csmui.py
# ya da tam yol:
& "C:\Users\<sen>\AppData\Local\Programs\Python\Python312\python.exe" csmui.py
```
CLI sürümü (`csm.py`) depo bulamazsa **tanı bilgisi** basar (hangi Python, hangi
yollar var/yok) — bu çıktıyı paylaşmanız sorunu hızlıca netleştirir.

**"tkinter bulunamadı"**
GUI için tkinter gerekir; python.org kurulumlarında hazır gelir. `py csmui.py` ile
deneyin.

**Liste güncellenmedi**
Uygulama session listesini yalnızca açılışta okur. Taşımadan sonra Claude'u tamamen
kapatıp yeniden açın.

---

## Lisans

[MIT](LICENSE)
