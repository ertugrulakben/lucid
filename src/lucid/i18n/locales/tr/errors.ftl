### Hata mesajları — kısa, eyleme dönük, gizli bilgi sızdırmaz.

# Yapılandırma / kurulum
err-no-api-key = API anahtarı tanımlı değil. `lucid setup` çalıştırın veya ANTHROPIC_API_KEY ayarlayın.
err-bad-config = Yapılandırma dosyası okunamadı: { $path }
err-bad-locale = Bilinmeyen dil: { $locale }. İngilizceye dönülüyor.

# Backend / ağ
err-backend-unreachable = Yapılandırılan backend'e ulaşılamıyor ({ $backend }).
err-backend-timeout = Backend { $seconds } saniye içinde yanıt vermedi.
err-backend-rate-limit = Hız sınırına ulaşıldı. { $seconds } sn sonra yeniden denenecek.
err-backend-auth = Backend kimlik bilgilerini reddetti. API anahtarınızı kontrol edin.

# Yakalama / masaüstü
err-capture-failed = Ekran yakalanamadı: { $reason }
err-window-not-found = Pencere bulunamadı: { $title }
err-element-not-found = Öğe bulunamadı: { $description }

# Yürütme / güvenlik
err-step-failed = Adım başarısız: { $reason }
err-budget-exceeded = Adım veya süre bütçesi aşıldı.
err-user-stopped = Kullanıcı durdurdu.
err-permission-denied = İzin reddedildi: { $resource }

# İş akışı / yeniden oynatma
err-workflow-not-found = Eşleşen iş akışı yok: { $name }
err-workflow-corrupt = İş akışı dosyası bozuk: { $path }
err-template-missing-var = Şablon değişkeni verilmedi: { $name }

# Genel
err-unexpected = Beklenmeyen hata: { $reason }
err-not-implemented = Henüz uygulanmadı: { $feature }
