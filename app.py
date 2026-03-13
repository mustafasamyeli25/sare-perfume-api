import os, csv, json, base64, re, logging, time, random
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ─────────────────────────────────────────────────────────
# ÇOKLU API ANAHTARI ROTASYONU — kota dolunca sıradakine geç
# Vercel'de env değişkeni olarak tanımla:
#   GEMINI_API_KEY_1, GEMINI_API_KEY_2, GEMINI_API_KEY_3 ...
# ─────────────────────────────────────────────────────────

def get_groq_keys():
    """GROQ_API_KEY ortam değişkeninden Groq anahtarlarını okur (virgülle ayrılabilir)."""
    keys = []
    val = os.environ.get("GROQ_API_KEY", "").strip()
    if val:
        for k in val.split(","):
            k = k.strip()
            if k:
                keys.append(k)
    for i in range(1, 10):
        k = os.environ.get(f"GROQ_API_KEY_{i}", "").strip()
        if k: keys.append(k)
    return list(dict.fromkeys(keys))

GROQ_KEYS = get_groq_keys()
if GROQ_KEYS:
    logging.info(f"{len(GROQ_KEYS)} Groq anahtarı yüklendi.")
else:
    logging.warning("GROQ_API_KEY bulunamadı — sadece Gemini kullanılacak.")

def get_api_keys():
    keys = []
    # GEMINI_API_KEY içinde virgülle ayrılmış birden fazla anahtar desteklenir
    # Örnek: AIza...1,AIza...2,AIza...3
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single:
        for k in single.split(","):
            k = k.strip()
            if k:
                keys.append(k)
    # Ayrı değişkenler de desteklenir: GEMINI_API_KEY_1, GEMINI_API_KEY_2 ...
    for i in range(1, 10):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if k:
            keys.append(k)
    return list(dict.fromkeys(keys))  # tekrarları kaldır

API_KEYS = get_api_keys()
if not API_KEYS:
    logging.error("Hiç GEMINI_API_KEY bulunamadı!")
else:
    logging.info(f"{len(API_KEYS)} adet API anahtarı yüklendi.")

# Gemini modelleri (yedek)
MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

# Groq modelleri (birincil — ücretsiz, hızlı, günde 14.400 istek)
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

CSV_FILE_NAME    = "products_export_1 (2).csv"
PLACEHOLDER_IMG  = "https://via.placeholder.com/150?text=Sare+Perfume"
PRODUCT_BASE_URL = "https://sareperfume.com/products/"

# ─────────────────────────────────────────────────────────
# ÜRÜN VERİTABANI
# ─────────────────────────────────────────────────────────
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB = {}
PERFUME_ALL_LINES = []  # tüm ürün satırları — akıllı filtreleme için

def clean_html(raw):
    if not raw: return ""
    return re.sub(r'\s+', ' ', re.sub(r'<.*?>', ' ', raw)).strip()

def load_products():
    global PERFUME_CATALOG_TEXT, PRODUCT_DB
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_FILE_NAME)
    if not os.path.exists(csv_path):
        logging.error(f"CSV bulunamadı: {csv_path}")
        PERFUME_CATALOG_TEXT = "HATA: Katalog bulunamadı."
        return
    lines, db = [], {}
    # Tüm ürünleri DB'ye yükle (resim/url için) ama AI'ya max 100 ürün gönder
    try:
        with open(csv_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                title = row.get('Title', '').strip()
                if not title: continue
                handle = row.get('Handle', '').strip()
                if handle not in db:
                    db[handle] = {
                        "title": title,
                        "image": row.get('Image Src', '').strip() or PLACEHOLDER_IMG,
                        "url"  : f"{PRODUCT_BASE_URL}{handle}"
                    }
                    tags = row.get('Tags','').strip()
                    lines.append(f"{handle}|{title}|{tags}")
        PRODUCT_DB = db
        PERFUME_ALL_LINES[:] = lines  # tüm ürün satırlarını sakla
        # Varsayılan katalog: rastgele 100 ürün — her deploy'da farklı başlangıç
        import random as _r
        shuffled = lines[:]
        _r.shuffle(shuffled)
        PERFUME_CATALOG_TEXT = "\n".join(shuffled[:100])
        logging.info(f"{len(db)} ürün yüklendi.")
    except Exception as e:
        logging.error(f"CSV yükleme hatası: {e}")
        PERFUME_CATALOG_TEXT = f"HATA: {e}"

load_products()


# ─────────────────────────────────────────────────────────
# AKILLI KATALOG FİLTRELEME
# Sorguya göre ilgili ürünleri filtreler, token tasarrufu sağlar
# ─────────────────────────────────────────────────────────
KOKU_KEYWORDS = {
    "odunsu"  : ["woody", "wood", "oud", "santal", "cedar", "patchouli", "odunsu"],
    "çiçeksi" : ["floral", "rose", "jasmine", "çiçek", "lavender", "violet", "flower"],
    "meyveli" : ["fruity", "fruit", "berry", "citrus", "meyve", "apple", "peach"],
    "baharatlı": ["spicy", "spice", "baharat", "pepper", "cinnamon", "cardamom"],
    "oryantal" : ["oriental", "amber", "musk", "oryantal", "vanilla", "resin"],
    "taze"    : ["fresh", "aqua", "marine", "taze", "green", "mint", "ocean"],
    "erkek"   : ["men", "homme", "erkek", "masculine"],
    "kadın"   : ["women", "femme", "kadın", "feminine", "pour femme"],
    "unisex"  : ["unisex", "nötr"],
}

def smart_catalog(query: str, max_items: int = 80) -> str:
    """Sorguya göre filtrelenmiş katalog döndürür. Eşleşme yoksa ilk max_items ürünü verir."""
    if not query or not PERFUME_ALL_LINES:
        return "\n".join(PERFUME_ALL_LINES[:max_items]) if PERFUME_ALL_LINES else PERFUME_CATALOG_TEXT

    query_lower = query.lower()
    matched_keys = []

    # Hangi kategoriler eşleşiyor?
    for category, words in KOKU_KEYWORDS.items():
        if any(w in query_lower for w in words):
            matched_keys.extend(words)

    if not matched_keys:
        # Eşleşme yok — sorgu kelimelerini doğrudan ürün satırlarında ara
        query_words = [w for w in query_lower.split() if len(w) > 2]
        matched = [l for l in PERFUME_ALL_LINES
                   if any(w in l.lower() for w in query_words)]
        unmatched = [l for l in PERFUME_ALL_LINES if l not in matched]
        # Eşleşmeyenleri karıştır — her seferinde farklı ürünler gelsin
        random.shuffle(unmatched)
        combined = matched[:max_items//2] + unmatched[:max_items - min(len(matched), max_items//2)]
        return "\n".join(combined[:max_items])

    # Eşleşen kategorideki ürünleri öne al, kalanları karıştır
    matched_lines = [l for l in PERFUME_ALL_LINES
                     if any(k in l.lower() for k in matched_keys)]
    other_lines   = [l for l in PERFUME_ALL_LINES if l not in matched_lines]
    random.shuffle(matched_lines)   # eşleşenler arasında da çeşitlilik
    random.shuffle(other_lines)
    combined = matched_lines[:max_items] + other_lines[:max(0, max_items - len(matched_lines))]

    logging.info(f"Katalog filtresi: {len(matched_lines)} eşleşen + {len(combined)-len(matched_lines)} ek ürün")
    return "\n".join(combined[:max_items])

# ─────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────

# Yazım hataları ve kısaltmalar dahil marka/parfüm eşleşme tablosu
MUADIL_MAP = {
    # Dior
    "sauvage": "dior sauvage", "savaş": "dior sauvage", "savaj": "dior sauvage",
    "dior savaş": "dior sauvage", "dior savaj": "dior sauvage",
    "miss dior": "miss dior", "j'adore": "jadore", "jadore": "jadore",
    "fahrenheit": "dior fahrenheit", "poison": "dior poison",
    # Chanel
    "no5": "chanel no5", "no 5": "chanel no5", "number 5": "chanel no5",
    "coco": "chanel coco mademoiselle", "coco mademoiselle": "chanel coco mademoiselle",
    "bleu": "bleu de chanel", "bleu de chanel": "bleu de chanel",
    "allure": "chanel allure", "chance": "chanel chance",
    # Tom Ford
    "ombre leather": "tom ford ombre leather", "ombre": "tom ford ombre leather",
    "black orchid": "tom ford black orchid", "tobacco vanille": "tom ford tobacco vanille",
    "lost cherry": "tom ford lost cherry", "neroli portofino": "tom ford neroli portofino",
    # Creed
    "aventus": "creed aventus", "silver mountain": "creed silver mountain water",
    "viking": "creed viking",
    # Armani
    "acqua di gio": "armani acqua di gio", "acqua": "armani acqua di gio",
    "si": "armani si", "code": "armani code",
    # YSL
    "ysl": "ysl", "libre": "ysl libre", "black opium": "ysl black opium",
    "opium": "ysl opium", "y edp": "ysl y",
    # Versace
    "eros": "versace eros", "dylan blue": "versace dylan blue",
    "bright crystal": "versace bright crystal",
    # Prada
    "candy": "prada candy", "luna rossa": "prada luna rossa",
    # Gucci
    "bloom": "gucci bloom", "guilty": "gucci guilty",
    # Diğerleri
    "baccarat": "baccarat rouge 540", "rouge 540": "baccarat rouge 540",
    "oud wood": "oud wood", "angel": "mugler angel",
    "la vie": "lancome la vie est belle", "la vie est belle": "lancome la vie est belle",
    "invictus": "paco rabanne invictus", "million": "paco rabanne 1 million",
    "1 million": "paco rabanne 1 million", "olympea": "paco rabanne olympea",
    "good girl": "carolina herrera good girl", "212": "carolina herrera 212",
    "boss": "hugo boss", "baldessarini": "baldessarini",
    "molecule": "escentric molecule", "molecules": "escentric molecule",
}

def normalize_query(query: str) -> str:
    """Yazım hatalarını ve kısaltmaları normalize et."""
    q = query.lower().strip()
    for alias, canonical in MUADIL_MAP.items():
        if alias in q:
            return canonical
    return q

def is_muadil_query(query: str) -> bool:
    """Kullanıcı orijinal bir parfüm adı mı arıyor?"""
    q = query.lower()
    # Direkt harita eşleşmesi
    if any(alias in q for alias in MUADIL_MAP):
        return True
    # Genel sinyal kelimeleri
    signals = ["muadil", "alternatif", "benzer", "yerine", "var mı", "var mi",
               "satıyor musunuz", "arıyorum", "ariyorum"]
    return any(s in q for s in signals)

def muadil_catalog(query: str) -> str:
    """Muadil araması için katalogdan ilgili ürünleri getir."""
    q_normalized = normalize_query(query)
    q_lower = query.lower()

    # Normalize edilmiş sorgudan anahtar kelimeler çıkar
    search_terms = set()
    for alias, canonical in MUADIL_MAP.items():
        if alias in q_lower:
            # Canonical'dan kelimeler al
            for word in canonical.split():
                if len(word) > 2:
                    search_terms.add(word)
            # Alias kelimelerini de ekle
            for word in alias.split():
                if len(word) > 2:
                    search_terms.add(word)

    # Sorgunun kendi kelimelerini de ekle
    for word in q_lower.split():
        if len(word) > 2:
            search_terms.add(word)

    # Katalogda ara
    matched = []
    for line in PERFUME_ALL_LINES:
        line_lower = line.lower()
        if any(term in line_lower for term in search_terms):
            matched.append(line)

    # Eşleşme yoksa tüm katalogu ver
    if not matched:
        all_lines = PERFUME_ALL_LINES[:]
        random.shuffle(all_lines)
        matched = all_lines[:80]

    logging.info(f"Muadil katalog: {len(search_terms)} terim, {len(matched)} ürün bulundu")
    return "\n".join(matched[:80])

def build_prompt(has_image, user_query=""):
    img_note = ""
    if has_image:
        img_note = (
            "\nGÖRÜNTÜ ANALİZİ: Meslek/üniforma etiketlerine takılma. "
            "Kişinin enerjisini, renk paletini, tarzını, ten tonunu ve ortam atmosferini oku. "
            "Ruhunu anla.\n"
        )

    # Muadil arama modu
    if user_query and not has_image and is_muadil_query(user_query):
        return (
            "Sen Sare Parfüm'ün uzman danışmanısın. Sare, dünyaca ünlü parfümlerin "
            "muadillerini üretiyor — aynı koku ailesi, çok daha uygun fiyat.\n\n"
            "KATALOG (format: handle|isim|etiketler):\n" + muadil_catalog(user_query) + "\n\n"
            "GÖREV: Müşterinin aradığı orijinal parfümün Sare muadilini katalogdan bul.\n"
            "ÖNEMLİ KURALLAR:\n"
            "1. Etiketlerde 'Muadili' kelimesi geçen veya orijinal parfüm/marka adı etiketlerde olan ürünü seç\n"
            "2. Müşteri tam adı yazamayabilir — 'dior savaş' = Dior Sauvage, 'bleu' = Bleu de Chanel gibi yorum yap\n"
            "3. Doğru muadili bulduysan 1 ürün yeterli, birden fazla seçenek varsa max 3 öner\n"
            "4. Açıklamada: hangi orijinal parfümün muadili olduğunu belirt, koku karakterini anlat, "
            "fiyat avantajından bahset\n\n"
            "SADECE JSON döndür:\n"
            '{"recommendations":[{"kimlik":"handle-degeri","aciklama":"açıklama"}]}'
        )

    # Normal öneri modu — duygusal, hikaye anlatıcı
    return (
        "Sen Sare Parfüm'ün koku uzmanısın. İnsan ruhunu, anları ve duyguları kokuya "
        "çevirebilen bir şairsin. Müşteriye reklam değil, gerçek bir deneyim sunarsın.\n\n"
        "KATALOG (format: handle|isim|etiketler):\n" + smart_catalog(user_query) + "\n\n" + img_note +
        "GÖREV: Müşterinin anlattığı an, ortam ve ruh haline göre katalogdan en uygun 3 parfümü seç.\n"
        "KRİTİK KURALLAR:\n"
        "1. ORTAMA UYGUNLUK: Sahil/deniz = taze, aqua, narenciye notalar. "
        "Spor = hafif, temiz, uzun süre yayılan. "
        "Akşam yemeği = oryantal, derin, kalıcı. "
        "Ofis = nötr, zarif, rahatsız etmeyen. "
        "Yanlış kategoriden asla önerme — sahil için ağır oud önermek yasak.\n"
        "2. AÇIKLAMA TARZI: Her parfüm için o anı yaşatır gibi yaz. "
        "Sahilde yürüyüş için: \'Dalga sesi arkanda, ayaklarının altında ıslak kum, "
        "burnuna ilk çarpan o tuz ve deniz kokusu — işte tam bu an için.\' "
        "Notaları teknik değil, duyusal anlat. Neden BU an için doğru olduğunu hissettir.\n"
        "3. KİŞİSELLEŞTİR: Müşterinin anlattığı detayları açıklamaya yansıt.\n\n"
        "SADECE JSON döndür:\n"
        '{"recommendations":[{"kimlik":"handle-degeri","aciklama":"3-4 cümle etkileyici açıklama"}]}'
    )

# ─────────────────────────────────────────────────────────
# GEMİNİ REST API ÇAĞRISI — çoklu anahtar + model fallback
# ─────────────────────────────────────────────────────────
def call_groq(prompt_text: str) -> str:
    """
    Groq API — LLaMA modeli, ücretsiz tier günde 14.400 istek.
    Görüntü desteği yok, sadece metin.
    """
    if not GROQ_KEYS:
        raise Exception("NO_GROQ_KEYS")

    keys_to_try = GROQ_KEYS.copy()
    random.shuffle(keys_to_try)

    for model in GROQ_MODELS:
        for key in keys_to_try:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt_text}],
                        "temperature": 0.85,
                        "max_tokens": 1024,
                        "response_format": {"type": "json_object"}
                    },
                    timeout=30
                )
                if r.status_code == 200:
                    logging.info(f"✅ Groq başarılı: {model}")
                    return r.json()["choices"][0]["message"]["content"]
                elif r.status_code == 429:
                    logging.warning(f"Groq 429: {model}, key=...{key[-6:]}")
                    time.sleep(0.5)
                    continue
                else:
                    logging.warning(f"Groq {r.status_code}: {r.text[:150]}")
                    continue
            except requests.Timeout:
                logging.warning(f"Groq timeout: {model}")
                continue
            except Exception as e:
                logging.warning(f"Groq hata: {e}")
                continue
    raise Exception("GROQ_FAILED")


def call_gemini(parts: list) -> dict:
    """Gemini yedek — Groq başarısız olursa."""
    if not API_KEYS:
        raise Exception("NO_KEYS")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 1024}
    }
    last_error = None
    for model in MODELS:
        for attempt in range(2):
            keys_to_try = API_KEYS.copy()
            random.shuffle(keys_to_try)
            if attempt == 1:
                time.sleep(3)
            for key in keys_to_try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={key}"
                )
                try:
                    r = requests.post(url, json=payload, timeout=30)
                    if r.status_code == 200:
                        logging.info(f"✅ Gemini yedek başarılı: {model}")
                        return r.json()
                    elif r.status_code in (429, 403):
                        last_error = "QUOTA"
                        time.sleep(0.3)
                        continue
                    elif r.status_code == 404:
                        last_error = "BAD_REQUEST"
                        break
                    elif r.status_code == 400:
                        body = r.json()
                        if "blocked" in str(body).lower():
                            raise Exception("BLOCKED")
                        last_error = "BAD_REQUEST"
                        break
                    else:
                        last_error = f"HTTP_{r.status_code}"
                        continue
                except requests.Timeout:
                    last_error = "TIMEOUT"
                    continue
                except Exception as e:
                    raise e
            else:
                continue
            break
    raise Exception(last_error or "ALL_FAILED")

# ─────────────────────────────────────────────────────────
# KULLANICI DOSTU HATALAR
# ─────────────────────────────────────────────────────────
ERROR_MAP = {
    "NO_KEYS"    : ("Servis yapılandırma hatası.", 500),
    "QUOTA"      : ("Koku uzmanımız şu an çok meşgul, lütfen birkaç saniye sonra tekrar dene.", 429),
    "BLOCKED"    : ("Bu içerik işlenemedi. Farklı bir şekilde yazar mısın?", 400),
    "TIMEOUT"    : ("Bağlantı zaman aşımına uğradı. Tekrar dene.", 504),
    "ALL_FAILED"    : ("Servis geçici olarak kullanılamıyor. Birazdan tekrar dene.", 503),
    "API_DISABLED" : ("Servis yapılandırma hatası. Lütfen bizimle iletişime geçin.", 503),
}

def err(kind, status=None):
    msg, default_status = ERROR_MAP.get(kind, ("Beklenmedik bir sorun oluştu.", 500))
    return jsonify({"error": msg}), (status or default_status)

# ─────────────────────────────────────────────────────────
# ANA ENDPOINT
# ─────────────────────────────────────────────────────────
@app.route("/recommend", methods=["POST"])
def recommend():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Geçersiz istek."}), 400

    user_query   = (data.get("query") or "").strip()
    image_base64 = data.get("image")

    if not user_query and not image_base64:
        return jsonify({"error": "Lütfen bir şeyler yazın veya fotoğraf yükleyin."}), 400

    has_image = bool(image_base64)
    parts = [{"text": build_prompt(has_image, user_query)}]

    if user_query:
        parts.append({"text": f"Müşteri mesajı: {user_query}"})

    if has_image:
        try:
            img_str   = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
            img_bytes = base64.b64decode(img_str)
            mime = "image/jpeg"
            if image_base64.startswith("data:image/png"):  mime = "image/png"
            elif image_base64.startswith("data:image/webp"): mime = "image/webp"
            parts.append({"inlineData": {"mimeType": mime, "data": img_str}})
        except Exception as e:
            logging.warning(f"Resim çözümleme hatası: {e}")
            return jsonify({"error": "Geçersiz resim formatı. JPG veya PNG yükle."}), 400

    # Groq önce dene (metin sorgusu veya sadece metin), Gemini yedek
    raw_json = None
    prompt_text = build_prompt(has_image, user_query)
    if user_query and not has_image and GROQ_KEYS:
        # Sadece metin → Groq kullan (daha hızlı ve cömert)
        try:
            full_prompt = prompt_text + f"\n\nMüşteri mesajı: {user_query}"
            raw_json = call_groq(full_prompt)
            logging.info("Groq ile yanıt alındı.")
        except Exception as e:
            logging.warning(f"Groq başarısız, Gemini'ye geçiliyor: {e}")
            raw_json = None

    if raw_json is None:
        # Groq yoksa veya başarısızsa Gemini dene
        try:
            gemini_response = call_gemini(parts)
            raw = gemini_response["candidates"][0]["content"]["parts"][0]["text"]
            raw_json = re.sub(r'^```(?:json)?', '', raw.strip()).rstrip('`').strip()
        except Exception as e:
            return err(str(e))

    try:
        data_parsed = json.loads(raw_json)
    except Exception as e:
        logging.error(f"JSON parse hatası: {e} | Ham: {str(raw_json)[:200]}")
        return err("ALL_FAILED")

    results = []
    for rec in data_parsed.get("recommendations", []):
        handle = (rec.get("kimlik") or "").strip()
        if handle and handle in PRODUCT_DB:
            p = PRODUCT_DB[handle]
            results.append({
                "title"      : p["title"],
                "url"        : p["url"],
                "image"      : p["image"],
                "description": (rec.get("aciklama") or "").strip()
            })
        else:
            logging.warning(f"Bilinmeyen handle: '{handle}'")

    if not results:
        return jsonify({"error": "Size özel öneri oluşturulamadı. Farklı bir şey dener misiniz?"}), 200

    return jsonify({"recommendations": results})



# ─────────────────────────────────────────────────────────
# TEST ENDPOINT — hangi anahtar/model çalışıyor?
# Tarayıcıdan: https://sare-perfume-api.vercel.app/test
# ─────────────────────────────────────────────────────────
@app.route("/test", methods=["GET"])
def test_keys():
    """Her key+model kombinasyonunu sırayla test eder (2s aralıkla - rate limit aşmaz)."""
    results = []
    test_payload = {
        "contents": [{"parts": [{"text": "Say hello."}]}],
        "generationConfig": {"maxOutputTokens": 5, "temperature": 0.1}
    }
    # Sadece birincil modeli test et, tüm keyler için
    model = MODELS[0]
    for i, key in enumerate(API_KEYS):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        try:
            r = requests.post(url, json=test_payload, timeout=10)
            ok = r.status_code == 200
            msg = "✅ ÇALIŞIYOR" if ok else r.json().get("error", {}).get("message", "?")[:100]
            results.append({
                "key_no"  : i + 1,
                "key_tail": f"...{key[-10:]}",
                "model"   : model,
                "status"  : r.status_code,
                "ok"      : ok,
                "msg"     : msg
            })
        except Exception as e:
            results.append({
                "key_no"  : i + 1,
                "key_tail": f"...{key[-10:]}",
                "model"   : model,
                "status"  : 0,
                "ok"      : False,
                "msg"     : str(e)[:100]
            })
        if i < len(API_KEYS) - 1:
            time.sleep(2)  # Rate limit aşmamak için bekle

    working = [r for r in results if r["ok"]]
    return jsonify({
        "total_keys"  : len(API_KEYS),
        "working_keys": len(working),
        "model_tested": model,
        "note"        : "Anahtarlar sırayla 2s aralıkla test edildi (rate limit güvenli)",
        "results"     : results
    })

# ─────────────────────────────────────────────────────────
# SAĞLIK KONTROLÜ
# ─────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status"   : "ok",
        "products" : len(PRODUCT_DB),
        "api_keys" : len(API_KEYS),
        "models"   : MODELS
    })

@app.route("/", methods=["GET"])
def index():
    return jsonify({"service": "Sare Perfume API", "status": "running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)
