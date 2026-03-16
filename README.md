# Gazete Hacettepe Haber API

Gazete Hacettepe (https://gazete.hacettepe.edu.tr/) haberlerini programatik olarak sunan REST API.

---

## Özellikler

- Haber listesi (sayfalama destekli)
- Haber detayı (tam metin, tüm görseller)
- Her haber için: başlık, özet, yazar, tarih, görsel URL'si, kaynak linki
- Otomatik Swagger UI dokümantasyonu

---

## Kurulum

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# Sunucuyu başlat
uvicorn main:app --reload --port 8000
```

---

## Endpointler

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/` | API bilgisi |
| GET | `/haberler` | Haber listesi (opsiyonel: `?page=2`) |
| GET | `/haberler/{slug}` | Tek haber detayı |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc dokümantasyonu |

---

## Örnek Kullanım

### Haber listesi
```
GET http://localhost:8000/haberler
```

```json
[
  {
    "title": "Türkiye'nin en kapsamlı Biyoçeşitlilik Müzesi Hacettepe'de açıldı",
    "summary": "Türlerin ve genlerin biyosferdeki serüvenlerinin keşfedileceği...",
    "author": "Yönetim",
    "date": "2023-05-22",
    "image_url": "https://gazete.hacettepe.edu.tr/fs_/HABERLER/2023/Mayıs/biyo1.jpeg",
    "url": "https://gazete.hacettepe.edu.tr/tr/haber/turkiyenin_en_kapsamli_biyocesitlilik_muzesi_hacettepede_acildi-419"
  }
]
```

### Haber detayı
```
GET http://localhost:8000/haberler/turkiyenin_en_kapsamli_biyocesitlilik_muzesi_hacettepede_acildi-419
```

```json
{
  "title": "Türkiye'nin en kapsamlı Biyoçeşitlilik Müzesi Hacettepe'de açıldı",
  "summary": "Türlerin ve genlerin biyosferdeki serüvenlerinin keşfedileceği...",
  "author": "Yönetim",
  "date": "2023-05-22",
  "image_url": "https://gazete.hacettepe.edu.tr/...",
  "url": "https://gazete.hacettepe.edu.tr/tr/haber/...",
  "content": "Tam haber metni buraya gelir...",
  "images": [
    "https://gazete.hacettepe.edu.tr/fs_/HABERLER/2023/Mayıs/biyo1.jpeg",
    "https://gazete.hacettepe.edu.tr/fs_/HABERLER/2023/Mayıs/biyo2.jpeg"
  ]
}
```

---

## Notlar

- API, Gazete Hacettepe sitesini anlık olarak scrape eder; önbellekleme yapılmaz.
- Sitede açık bir "yazar" alanı bulunmadığı için `author` alanı haber kategorisini döner.
- Tarih bilgisi detay sayfasında varsa ISO 8601 formatında (`YYYY-MM-DD`) döner.