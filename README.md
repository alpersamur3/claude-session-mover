# Claude Session Mover · Claude Sohbet Taşıyıcı

**Dil / Language:  [🇹🇷 Türkçe](#tr) · [🇬🇧 English](#en)**

Claude masaüstü uygulamasındaki sohbetleri bir hesaptan diğerine taşıyan küçük bir
araç. / A small tool that moves Claude desktop chats from one account to another.

| Dosya / File | Tür / Type | Açıklama / Description |
|--------------|------------|------------------------|
| [`csm.py`](csm.py)   | Terminal (CLI)   | Soru-cevap akışı / Interactive prompts |
| [`csmui.py`](csmui.py) | Tkinter (GUI)  | Liste, önizleme, boyut karşılaştırması / List, preview, size compare |
| [`i18n.py`](i18n.py)  | Ortak / Shared | TR/EN çeviriler / TR/EN translations |

> ⚠️ **Resmî değildir / Unofficial.** Kendi sorumluluğunuzda kullanın. Use at your own risk.

---

<a id="tr"></a>
## 🇹🇷 Türkçe

### Sorun: "Sohbetim diğer hesapta kaldı, bu hesapta görünmüyor"

Claude masaüstü uygulaması, sohbet **listeleme kayıtlarını hesap bazında** ayrı
klasörlerde tutar:

```
<base>\<hesap-id>\<workspace-id>\local_<uuid>.json
```

Uygulama yalnızca **o an giriş yapılı hesabın** klasörünü okur. Başka bir hesapta
açılmış sohbet bu yüzden listede görünmez — ama **silinmemiştir**.

- **Sohbet metni (transkript)** `~/.claude/projects\...\<cliSessionId>.jsonl` altında,
  **ortaktır ve hesaba bağlı değildir.**
- Hesaba bağlı olan tek şey **listeleme kaydı** (`local_*.json`).

Bu araç sadece o küçük listeleme kaydını hedef hesaba kopyalar.

Kayıt dosyasının iki kilit alanı:
- `sessionId` → `local_<uuid>` (dosya adıyla **aynıdır**)
- `cliSessionId` → asıl transkript `.jsonl` dosyasını işaret eder

### Gereksinim
- **Python 3.8+** (gerçek kurulum; Microsoft Store/sandbox Python **önerilmez**).
- GUI için **tkinter** (python.org kurulumlarında hazır gelir).
- Ek bağımlılık yok (yalnızca standart kütüphane).

### Kullanım
Windows'ta **`py` launcher** en güvenlisidir (gerçek Python'a gider):

```powershell
py csmui.py            # Grafik arayüz (Türkçe)
py csmui.py --en       # Grafik arayüz (İngilizce)
py csm.py              # Terminal
py csm.py --en         # Terminal (İngilizce)
```

GUI'de sağ üstten **TR/EN** dilini anında değiştirebilirsiniz.

**Adımlar:**
1. **Claude masaüstü uygulamasını tamamen kapatın** (sistem tepsisinden de çıkın).
2. Aracı çalıştırın.
3. **Kaynak hesabı** seçin → sohbetler listelenir.
4. Taşımak istediğiniz sohbet(ler)i seçin.
5. **Hedef hesabı** seçin (kaynak listede çıkmaz).
6. Taşıyın. Çakışma varsa boyutları görüp **üzerine yaz / atla** kararını verin.
7. Claude'u yeniden açın; sohbet hedef hesapta görünür (GUI'de **🔄 Yenile**).

### Çakışma ve "üzerine yazma"
Hedefte aynı sohbet zaten varsa araç sessizce atlamaz; uyarır ve **boyut
karşılaştırması** gösterir. "Aynı sohbet": aynı `cliSessionId` **veya** aynı
`sessionId` (= dosya adı).

> Aynı dosya adı **farklı** bir sohbeti gösterebilir (örn. eski hesapta dolu sohbet
> vs. yeni hesapta küçük bir "stub"). Bu yüzden boyutlar gösterilip onay istenir.

### Deneme modu (ekran görüntüsü için)
Repo, `sample-data/` altında **dummy hesaplar + sohbetler** içerir. Gerçek
verinize dokunmadan arayüzü denemek/ekran görüntüsü almak için:

```powershell
py csmui.py --demo
py csm.py --demo
```

Demo modu yalnızca `sample-data/` klasörünü okur/yazar. Üzerine yazma denersen
`git restore sample-data` ile sıfırlayabilirsin.

### Güvenlik / Geri alma
- Araç kaynak kaydı **kopyalar**; orijinal yerinde kalır.
- **Üzerine yazma** hedefteki mevcut kaydı değiştirir; gerekirse önce yedek alın.
- Yalnızca `local_*.json` taşınır; transkriptlere dokunulmaz.

### Nasıl çalışır (teknik)
- Tüm olası depo konumları taranır ve **gerçek yola (`realpath`) çözülür**:
  - `%APPDATA%\Claude\claude-code-sessions`
  - `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code-sessions`
    (MSIX/Store kurulum)
- Yazma, fiziksel olarak benzersiz **tüm depolara aynalanır**.
- MSIX kurulumda `%APPDATA%\Claude` paket konteynerine giden bir **symlink**'tir;
  araç bunu çözerek doğrudan gerçek konuma yazar.

### Sorun Giderme
**"Session deposu bulunamadı"** → Büyük olasılıkla **Store/sandbox Python**
kullanıyorsunuz; MSIX symlink'ini takip edemez. Gerçek Python ile çalıştırın:
```powershell
py csmui.py
# veya tam yol:
& "C:\Users\<sen>\AppData\Local\Programs\Python\Python312\python.exe" csmui.py
```
`csm.py` depo bulamazsa **tanı bilgisi** basar (hangi Python, hangi yollar).

**"tkinter bulunamadı"** → GUI için tkinter gerekir; `py csmui.py` ile deneyin.

**Liste güncellenmedi** → Uygulama listeyi yalnızca açılışta okur; Claude'u kapatıp
yeniden açın.

<!-- Ekran görüntüleri: docs/ klasörüne ekleyip aşağıdaki satırları açın
![Ana ekran](docs/main-tr.png)
![Çakışma](docs/conflict-tr.png)
-->

---

<a id="en"></a>
## 🇬🇧 English

### Problem: "My chat is in another account and doesn't show here"

The Claude desktop app stores chat **listing records per account** in separate
folders:

```
<base>\<account-id>\<workspace-id>\local_<uuid>.json
```

The app only reads the folder of the **currently signed-in account**. A chat opened
under a different account therefore won't appear in the list — but it is **not
deleted**.

- The **chat transcript** lives under `~/.claude/projects\...\<cliSessionId>.jsonl`,
  is **shared and account-independent.**
- The only account-bound thing is the **listing record** (`local_*.json`).

This tool only copies that small listing record to the target account.

Two key fields of the record:
- `sessionId` → `local_<uuid>` (**equals** the file name)
- `cliSessionId` → points to the actual transcript `.jsonl`

### Requirements
- **Python 3.8+** (a real install; Microsoft Store/sandbox Python **not recommended**).
- **tkinter** for the GUI (bundled with python.org installers).
- No extra dependencies (standard library only).

### Usage
On Windows the **`py` launcher** is safest (uses a real Python):

```powershell
py csmui.py            # GUI (Turkish)
py csmui.py --en       # GUI (English)
py csm.py              # CLI
py csm.py --en         # CLI (English)
```

In the GUI you can switch **TR/EN** instantly from the top-right.

**Steps:**
1. **Fully close the Claude desktop app** (quit from the system tray too).
2. Run the tool.
3. Select the **source account** → chats are listed.
4. Select the chat(s) to move.
5. Select the **target account** (the source is excluded from the list).
6. Move. On conflicts, review sizes and choose **overwrite / skip**.
7. Reopen Claude; the chat appears in the target account (in the GUI click **🔄 Refresh**).

### Conflicts and "overwrite"
If the same chat already exists in the target, the tool does not skip silently; it
warns and shows a **size comparison**. "Same chat" means the same `cliSessionId`
**or** the same `sessionId` (= file name).

> The same file name may point to a **different** chat (e.g. a full chat in the old
> account vs. a small "stub" in the new one). That's why sizes are shown before you
> confirm.

### Demo mode (for screenshots)
The repo ships **dummy accounts + chats** under `sample-data/`. To try the UI / take
screenshots without touching your real data:

```powershell
py csmui.py --demo
py csm.py --demo
```

Demo mode only reads/writes `sample-data/`. If you test an overwrite, reset it with
`git restore sample-data`.

### Safety / Undo
- The tool **copies** the source record; the original stays in place.
- **Overwrite** replaces the existing target record; back it up first if unsure.
- Only `local_*.json` is moved; transcripts are never touched.

### How it works (technical)
- All candidate store locations are scanned and **resolved to their real path
  (`realpath`)**:
  - `%APPDATA%\Claude\claude-code-sessions`
  - `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code-sessions`
    (MSIX/Store install)
- Writes are **mirrored to every physically-unique store**.
- On MSIX installs `%APPDATA%\Claude` is a **symlink** into the package container; the
  tool resolves it and writes to the real location directly.

### Troubleshooting
**"No session store found"** → You are most likely using a **Store/sandbox Python**
that cannot follow the MSIX symlink. Run with a real Python:
```powershell
py csmui.py
# or full path:
& "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe" csmui.py
```
If `csm.py` finds no store it prints **diagnostics** (which Python, which paths).

**"tkinter not found"** → The GUI needs tkinter; try `py csmui.py`.

**List didn't update** → The app reads the list only at startup; close and reopen Claude.

<!-- Screenshots: drop files into docs/ and uncomment
![Main](docs/main-en.png)
![Conflict](docs/conflict-en.png)
-->

---

## Lisans / License

[MIT](LICENSE)
