### Lucid arayüz metinleri (overlay, diyaloglar, durum)

# Overlay kabuğu
overlay-title = Lucid
overlay-placeholder = Bir istek yazın, görsel yapıştırın veya Tab ile mod değiştirin
overlay-mode-answer = Cevapla
overlay-mode-teach = Öğret
overlay-mode-execute = Yürüt
overlay-hint-submit = Göndermek için Enter
overlay-hint-dismiss = Kapatmak için Esc
overlay-hint-mode-cycle = Mod değiştirmek için Tab

# System tepsisi
tray-tooltip = Lucid çalışıyor. Açmak için kısayol tuşuna basın.
tray-menu-show = Overlay'i göster
tray-menu-settings = Ayarlar
tray-menu-pause = Kısayolu duraklat
tray-menu-resume = Kısayolu sürdür
tray-menu-quit = Lucid'ten çık

# Ayarlar diyaloğu
settings-title = Lucid Ayarları
settings-tab-general = Genel
settings-tab-backend = Model ve Backend
settings-tab-overlay = Overlay
settings-tab-memory = Hafıza
settings-tab-safety = Güvenlik
settings-tab-advanced = Gelişmiş
settings-save = Kaydet
settings-cancel = İptal
settings-reset = Varsayılana sıfırla
settings-locale = Arayüz dili
settings-hotkey = Genel kısayol
settings-restart-required = Bazı değişiklikler yeniden başlatma sonrası geçerli olur.

# Onay diyalogları
confirm-destructive-title = İşlemi onayla
confirm-destructive-body = Lucid geri alınması zor bir işlem yapacak. Devam edilsin mi?
confirm-button-yes = Devam et
confirm-button-no = Durdur

# Genel
button-ok = Tamam
button-cancel = İptal
button-close = Kapat
button-retry = Yeniden dene
loading = Yükleniyor...

# Üst araç çubuğu
toolbar-attach-image = 📎 Görsel ekle
toolbar-attach-tooltip = Referans görsel ekle (PNG/JPG/WebP). Ctrl+V panodan yapıştırır.
toolbar-workflows = 💾 İş akışları
toolbar-workflows-tooltip = Öğret modunda kaydettiğiniz iş akışları — çalıştırmak için tıklayın.
toolbar-schedule = 🕘 Zamanlanmış görevler
toolbar-schedule-tooltip = Cron / her N / tek seferlik görevler — şimdi çalıştır veya dosyayı aç.
toolbar-actions = 📜 Eylemler
toolbar-actions-tooltip = Son 10 eylem panelini aç/kapat (Yürüt modu hata ayıklama).
toolbar-steps = 🎞 Adımlar
toolbar-steps-tooltip = Adım Galerisi'ni aç/kapat -- bu Yürüt çalışmasının görsel önce/sonra tarihçesi.
toolbar-thoughts = 🧠 Düşünceler
toolbar-thoughts-tooltip = Düşünce Zinciri panelini aç/kapat -- Lucid çalışırken canlı anlatım + plan işaretleri.

# Düşünce zinciri
thought-empty = Düşünce zinciri boşta.
thought-active = Düşünce zinciri -- { $count } kayıt
thought-clear = Temizle
toolbar-stop = ⏹ Durdur  (Ctrl+Shift+K)

# Adım galerisi
step-gallery-empty = Adım galerisi -- Yürüt modunda bir şey çalıştır, burası dolsun.
step-gallery-active = Aktif oturum: { $name }
step-gallery-loaded = Yüklü oturum { $name } -- { $count } adım
step-detail-before = Önce
step-detail-after = Sonra

# Pencere kontrolleri
window-minimize = ▁
window-minimize-tooltip = Tepsiye küçült (Ctrl+M). Kısayol yeniden açar.
window-dock = 🧷
window-dock-tooltip = Aktif ekranın köşesine yapıştır (Ctrl+D).
window-close = ✕
window-close-tooltip = Overlay'i kapat (Esc).

# Durum / yer tutucular
status-shortcuts = Ctrl+N: yeni sohbet   Esc: kapat   Ctrl+M: küçült   Ctrl+D: köşeye yapış
status-working = Claude çalışıyor…  yönlendirmek için yeni prompt + Enter
status-error = Hata
status-done = Tamam. Sonraki adımı yazın + Enter, veya Esc ile kapatın.
status-new = Yeni sohbet. İstediğinizi sorun.
status-click-through-on = Geçirgen mod AÇIK  (Ctrl+Alt+T ile değiştir)
status-click-through-off = Geçirgen mod KAPALI  (Ctrl+Alt+T ile değiştir)
status-working-mode = Çalışıyor… ({ $mode })

placeholder-answer = Lucid'e sor…  (Ctrl+1/2/3 mod değiştirir, Tab döner)
placeholder-teach = Ne öğreteceğinizi yazın…  (Enter ile overlay gizlenir, kısayolla kayıt durur)
placeholder-execute = Lucid'e YAPMAsı gerekeni söyle…  (fareyi ve klavyeyi devralır)

# İş akışı / zamanlama menüleri
menu-no-workflows = Henüz kayıtlı iş akışı yok
menu-how-to-record = Nasıl kaydederim? Ctrl+Alt+J → Ctrl+2 (Öğret)
menu-no-tasks = Henüz zamanlanmış görev yok
menu-add-task = Ekle: lucid schedule add --cron "0 9 * * *" --prompt "…"
menu-open-schedule-file = scheduled_tasks.json dosyasını aç

# Mod seçici
mode-answer = Cevapla
mode-teach = Öğret
mode-execute = Yürüt

# Tepsi menüsü
tray-tooltip-base = Lucid — { $hotkey }
tray-tooltip-recording = Lucid — KAYIT (durdurmak için { $hotkey })
tray-tooltip-executing = Lucid — YÜRÜTÜYOR (durdurmak için Ctrl+Shift+K)
tray-open = Aç
tray-new-conversation = Yeni sohbet
tray-saved-workflows = Kayıtlı iş akışları
tray-scheduled-tasks = Zamanlanmış görevler
tray-no-workflows = (Yok — Öğret moduyla kaydedin)
tray-no-schedules = (Yok — lucid schedule add …)
tray-settings = Ayarlar…
tray-open-settings-file = settings.yaml dosyasını aç
tray-quit = Çık
tray-settings-saved-title = Lucid — Ayarlar kaydedildi
tray-settings-saved-body = Backend değişti. Etkinleştirmek için tepsiden çıkıp yeniden başlatın.
