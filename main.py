"""
Gazete Hacettepe News API
Haberleri scrape ederek REST API üzerinden sunar.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import re

app = FastAPI(
    title="Gazete Hacettepe Haber API",
    description="Gazete Hacettepe (https://gazete.hacettepe.edu.tr/) haberlerini sunan REST API.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://gazete.hacettepe.edu.tr"


# ---------- Modeller ----------

class NewsItem(BaseModel):
    title: str
    summary: str
    author: Optional[str] = None
    date: Optional[str] = None
    image_url: Optional[str] = None
    url: str


class NewsDetail(NewsItem):
    content: str
    images: List[str] = []


class APIInfo(BaseModel):
    name: str
    version: str
    description: str
    endpoints: dict


# ---------- Yardımcı Fonksiyonlar ----------

async def fetch_page(url: str) -> BeautifulSoup:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HacettepeNewsAPI/1.0)"
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_date(raw: str) -> Optional[str]:
    """DD.MM.YYYY → ISO 8601"""
    raw = raw.strip()
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
        except ValueError:
            pass
    return raw or None


def clean_src(path: str) -> str:
    """Sitenin HTML'indeki bozuk src degerlerini temizler: \"/path/\" -> /path/"""
    if not path:
        return ""
    # Ters slash ve tirnaklari kaldir
    path = path.replace('\\"', '').replace("\\'", "").strip('"').strip("'").strip()
    return path


def abs_url(path: str) -> str:
    if not path:
        return ""
    path = clean_src(path)
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return BASE_URL + ("" if path.startswith("/") else "/") + path


def parse_listing_page(soup: BeautifulSoup) -> List[NewsItem]:
    """Ana sayfa / haberler listesinden haber kartlarını çeker."""
    items: List[NewsItem] = []

    # Her haber bir <div> bloku içinde başlık + özet + devamı linki ile geliyor
    # Siteye özgü: h2 ya da h3 başlık, p özet, a[href*="/haber/"] link
    seen_urls = set()

    for anchor in soup.select("a[href*='/haber/']"):
        href = anchor.get("href", "")
        full_url = abs_url(href)
        if full_url in seen_urls:
            continue

        # Başlığı bul: anchor içindeki metin ya da bir üst/kardeş başlık
        title = anchor.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        # "Devamı..." gibi linkleri atla, ancak bunların parent'ından haber bilgisi toplayabiliriz
        if "devamı" in title.lower() or "more" in title.lower():
            parent = anchor.find_parent(["div", "article", "li", "section"])
            if parent:
                heading = parent.find(["h1", "h2", "h3", "h4"])
                title = heading.get_text(strip=True) if heading else ""
                if not title:
                    continue
            else:
                continue

        seen_urls.add(full_url)

        # Özet: linkin en yakın kapsayıcısındaki <p>
        summary = ""
        parent = anchor.find_parent(["div", "article", "li", "section"])
        if parent:
            p = parent.find("p")
            if p:
                summary = p.get_text(strip=True)

        # Görsel
        image_url = None
        if parent:
            img = parent.find("img")
            if img and img.get("src"):
                src = img["src"]
                if "spacer" not in src:
                    image_url = abs_url(src)

        items.append(NewsItem(
            title=title,
            summary=summary,
            author=None,   # Listede yazar bilgisi yok
            date=None,     # Listede tarih bazen yok
            image_url=image_url,
            url=full_url,
        ))

    return items


async def scrape_news_list(page: int = 1) -> List[NewsItem]:
    """
    Haberler listesi sayfasından URL'leri alır,
    ardından her haberin detay sayfasını paralel olarak çekip tam bilgiyi döner.
    """
    import asyncio

    if page == 1:
        url = f"{BASE_URL}/tr/haberler"
    else:
        url = f"{BASE_URL}/tr/haberler?page={page}"

    soup = await fetch_page(url)
    stubs = parse_listing_page(soup)  # sadece title + url dolu

    async def fetch_item(stub: NewsItem) -> NewsItem:
        try:
            detail = await scrape_news_detail(stub.url)
            return NewsItem(
                title=detail.title,
                summary=detail.summary,
                author=detail.author,
                date=detail.date,
                image_url=detail.image_url,
                url=detail.url,
            )
        except Exception:
            return stub  # hata olursa stub'ı döndür

    results = await asyncio.gather(*[fetch_item(s) for s in stubs])
    return list(results)


async def scrape_news_detail(news_url: str) -> NewsDetail:
    """Tek bir haberin detay sayfasını scrape eder."""
    soup = await fetch_page(news_url)

    # Başlık
    title_tag = soup.find("h1") or soup.find("h2")
    title = title_tag.get_text(strip=True) if title_tag else "Başlık bulunamadı"

    # İçerik: h1'den sonra gelen tüm p ve img etiketleri
    # Sitenin yapısında belirli bir content div'i yok; h1 sonrasındaki her şeyi alıyoruz
    content_parts = []
    images = []

    if title_tag:
        for sibling in title_tag.find_next_siblings():
            tag_name = sibling.name
            # Kenar çubuğu / footer'a girince dur
            if tag_name in ("footer", "nav"):
                break
            # "Son Başlıklar" gibi sidebar bloklarını atla
            text_check = sibling.get_text(strip=True)
            if "Son Başlıklar" in text_check or "Paylaş" in text_check:
                break
            # Paragrafları topla
            if tag_name == "p":
                t = sibling.get_text(strip=True)
                if t:
                    content_parts.append(t)
            # Div içindeki paragrafları da topla
            elif tag_name == "div":
                for p in sibling.find_all("p"):
                    t = p.get_text(strip=True)
                    if t:
                        content_parts.append(t)
                for img in sibling.find_all("img"):
                    src = img.get("src", "")
                    if src and "spacer" not in src:
                        images.append(abs_url(src))
            # Görselleri topla
            for img in sibling.find_all("img"):
                src = img.get("src", "")
                if src and "spacer" not in src:
                    full = abs_url(src)
                    if full not in images:
                        images.append(full)

    # Paragraf bulunamadıysa tüm sayfadan dene (navbar/footer hariç)
    if not content_parts:
        body = soup.find("body")
        if body:
            all_p = body.find_all("p")
            for p in all_p:
                t = p.get_text(strip=True)
                if t and len(t) > 40:
                    content_parts.append(t)

    content = "\n\n".join(content_parts)

    # Özet: ilk paragraf
    summary = content_parts[0] if content_parts else ""
    if len(summary) > 350:
        summary = summary[:350] + "..."

    # Yazar: sitede açık yazar alanı yok; kategori etiketini kullanıyoruz
    author = None
    author_tag = soup.find("a", href=re.compile(r"/haberler/[a-z]"))
    if author_tag:
        author = author_tag.get_text(strip=True)

    # Tarih: sidebar'daki "Son Başlıklar" içindeki ilk tarih bu habere ait DEĞİL.
    # Slug içindeki numarayı referans al; sayfada açık tarih yoksa None döndür.
    date = None
    # Sayfada DD.MM.YYYY formatında tarih ara (sidebar hariç)
    sidebar = soup.find(string=re.compile(r"Son Başlıklar|Son Haberler"))
    sidebar_parent = sidebar.find_parent() if sidebar else None

    for text_node in soup.find_all(string=re.compile(r"\d{2}\.\d{2}\.\d{4}")):
        # Sidebar içindeyse atla
        if sidebar_parent and sidebar_parent in text_node.find_parents():
            continue
        date = parse_date(str(text_node))
        if date:
            break

    return NewsDetail(
        title=title,
        summary=summary,
        author=author,
        date=date,
        image_url=images[0] if images else None,
        images=images,
        content=content,
        url=news_url,
    )


# ---------- Endpointler ----------

@app.get("/", response_model=APIInfo, summary="API bilgisi")
async def root():
    return APIInfo(
        name="Gazete Hacettepe Haber API",
        version="1.0.0",
        description="Gazete Hacettepe haberlerini programatik olarak sunar.",
        endpoints={
            "GET /haberler": "Haber listesi (sayfalama: ?page=1)",
            "GET /haberler/{slug}": "Tek haber detayı (slug: URL'deki haber adı)",
            "GET /docs": "Swagger UI",
            "GET /redoc": "ReDoc dokümantasyonu",
        },
    )


@app.get("/haberler", response_model=List[NewsItem], summary="Haber listesi")
async def get_news(page: int = Query(default=1, ge=1, description="Sayfa numarası")):
    """
    Gazete Hacettepe haberler sayfasından haber listesini döner.

    Her haber için:
    - **title**: Haberin başlığı
    - **summary**: Kısa özet
    - **author**: Yazar / kategori
    - **date**: ISO 8601 tarih (varsa)
    - **image_url**: Kapak görseli URL'si (varsa)
    - **url**: Haberin tam URL'si
    """
    try:
        news = await scrape_news_list(page)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Kaynak siteye erişilemedi: {e}")
    if not news:
        raise HTTPException(status_code=404, detail="Bu sayfada haber bulunamadı.")
    return news


@app.get("/haberler/{slug}", response_model=NewsDetail, summary="Haber detayı")
async def get_news_detail(slug: str):
    """
    Belirtilen slug'a sahip haberin tam detayını döner.

    **slug** örneği: `turkiyenin_en_kapsamli_biyocesitlilik_muzesi_hacettepede_acildi-419`

    Ek olarak **content** (tam metin) ve **images** (tüm görseller) alanları da döner.
    """
    news_url = f"{BASE_URL}/tr/haber/{slug}"
    try:
        detail = await scrape_news_detail(news_url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Haber bulunamadı.")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Kaynak siteye erişilemedi: {e}")
    return detail