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

# Model tercihi — önce hız/kota dengesi iyi olan
MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

CSV_FILE_NAME    = "products_export_1 (2).csv"
PLACEHOLDER_IMG  = "https://via.placeholder.com/150?text=Sare+Perfume"
PRODUCT_BASE_URL = "https://sareperfume.com/products/"

# ─────────────────────────────────────────────────────────
# ÜRÜN VERİTABANI
# ─────────────────────────────────────────────────────────
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB = {}

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
                    lines.append(
                        f"ID:{handle}|İSİM:{title}|TAGS:{row.get('Tags','').strip()}"
                        f"|DETAY:{clean_html(row.get('Body (HTML)',''))[:300]}"
                    )
        PERFUME_CATALOG_TEXT = "\n".join(lines)
        PRODUCT_DB = db
        logging.info(f"{len(db)} ürün yüklendi.")
    except Exception as e:
        logging.error(f"CSV yükleme hatası: {e}")
        PERFUME_CATALOG_TEXT = f"HATA: {e}"

load_products()

# ─────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────
def build_prompt(has_image):
    img_note = ""
    if has_image:
        img_note = (
            "\nGÖRÜNTÜ ANALİZİ: Meslek/üniforma etiketlerine takılma. "
            "Kişinin enerjisini, renk paletini, tarzını, ten tonunu ve ortam atmosferini oku. "
            "Ruhunu anla.\n"
        )
    return (
        "Sen dünyanın en iyi parfüm butiklerinden birinde çalışan, insan ruhunu ve kokuları "
        "derinlemesine bilen bir uzmanısın. Müşterilere reklam değil, gerçek bir dost gibi "
        "konuşursun — sıcak, özgün, biraz gizemli. Klişe cümleler hiç kullanmazsın.\n\n"
        "KATALOG:\n" + PERFUME_CATALOG_TEXT + "\n\n" + img_note +
        "GÖREV: Müşterinin mesajı veya fotoğrafından yola çıkarak katalogdan en uygun 3 parfümü seç. "
        "Her biri için 2-3 cümlelik, KİŞİYE ÖZEL, etkileyici bir açıklama yaz. "
        "Onun hakkında fark ettiğin özgün bir detaydan başla.\n\n"
        "SADECE JSON döndür, başka hiçbir şey yazma:\n"
        '{"recommendations":[{"kimlik":"handle-degeri","aciklama":"2-3 cümle"}]}'
    )

# ─────────────────────────────────────────────────────────
# GEMİNİ REST API ÇAĞRISI — çoklu anahtar + model fallback
# ─────────────────────────────────────────────────────────
def call_gemini(parts: list) -> dict:
    """
    Tüm anahtarları dener. 429'da kısa bekleyip tekrar dener (max 2 tur).
    """
    if not API_KEYS:
        raise Exception("NO_KEYS")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 1024
        }
    }

    last_error = None

    for model in MODELS:
        # Her model için anahtarları 2 tur dene (ilk tur hızlı, ikinci tur bekleyerek)
        for attempt in range(2):
            keys_to_try = API_KEYS.copy()
            random.shuffle(keys_to_try)

            if attempt == 1:
                logging.info(f"Tüm keyler 429 verdi, 3s bekleyip tekrar deneniyor: {model}")
                time.sleep(3)

            for key in keys_to_try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={key}"
                )
                try:
                    r = requests.post(url, json=payload, timeout=30)
                    if r.status_code == 200:
                        logging.info(f"✅ Başarılı: model={model}, key=...{key[-6:]}")
                        return r.json()
                    elif r.status_code == 429:
                        logging.warning(f"429: model={model}, key=...{key[-6:]}")
                        last_error = "QUOTA"
                        time.sleep(0.2)
                        continue
                    elif r.status_code == 403:
                        logging.warning(f"403 API aktif değil: key=...{key[-6:]}")
                        last_error = "API_DISABLED"
                        continue
                    elif r.status_code == 404:
                        logging.warning(f"404 model yok: {model}")
                        last_error = "BAD_REQUEST"
                        break  # sonraki modele geç
                    elif r.status_code == 400:
                        body = r.json()
                        if "blocked" in str(body).lower():
                            raise Exception("BLOCKED")
                        logging.warning(f"400: {body}")
                        last_error = "BAD_REQUEST"
                        break
                    else:
                        logging.warning(f"HTTP {r.status_code}: {r.text[:150]}")
                        last_error = f"HTTP_{r.status_code}"
                        continue
                except requests.Timeout:
                    logging.warning(f"Timeout: {model}, key=...{key[-6:]}")
                    last_error = "TIMEOUT"
                    continue
                except Exception as e:
                    raise e
            else:
                continue  # iç döngü break ile çıkmadıysa devam et
            break  # 404/400 ile break → dış döngüye (model döngüsüne) geç

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
    parts = [{"text": build_prompt(has_image)}]

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

    try:
        gemini_response = call_gemini(parts)
    except Exception as e:
        return err(str(e))

    # Yanıtı ayrıştır
    try:
        raw = gemini_response["candidates"][0]["content"]["parts"][0]["text"]
        raw = re.sub(r'^```(?:json)?', '', raw.strip()).rstrip('`').strip()
        data_parsed = json.loads(raw)
    except Exception as e:
        logging.error(f"JSON parse hatası: {e} | Yanıt: {gemini_response}")
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
    results = []
    test_payload = {
        "contents": [{"parts": [{"text": "Say hello in one word."}]}],
        "generationConfig": {"maxOutputTokens": 20, "temperature": 0.1}
    }
    for model in MODELS:
        for key in API_KEYS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={key}"
            )
            try:
                r = requests.post(url, json=test_payload, timeout=10)
                results.append({
                    "model": model,
                    "key_tail": f"...{key[-8:]}",
                    "status": r.status_code,
                    "ok": r.status_code == 200,
                    "msg": r.json().get("error", {}).get("message", "OK")[:120] if r.status_code != 200 else "✅ ÇALIŞIYOR"
                })
                if r.status_code == 200:
                    break  # bu model çalışıyor, diğer keyleri test etme
            except Exception as e:
                results.append({
                    "model": model,
                    "key_tail": f"...{key[-8:]}",
                    "status": 0,
                    "ok": False,
                    "msg": str(e)[:120]
                })
    working = [r for r in results if r["ok"]]
    return jsonify({
        "total_keys": len(API_KEYS),
        "working_combinations": len(working),
        "results": results
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
