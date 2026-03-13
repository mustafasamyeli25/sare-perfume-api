import os
import csv
import json
import base64
import re
import logging
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
# YAPILANDIRMA
# ─────────────────────────────────────────────
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY")
CSV_FILE_NAME    = "products_export_1 (2).csv"
PLACEHOLDER_IMG  = "https://via.placeholder.com/150?text=Sare+Perfume"
PRODUCT_BASE_URL = "https://sareperfume.com/products/"
MODEL_NAME       = "gemini-2.0-flash"   # gemini-2.5-flash / gemini-1.5-flash da kullanılabilir

# ─────────────────────────────────────────────
# GEMINİ İSTEMCİSİ
# ─────────────────────────────────────────────
client = None
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY ortam değişkeni eksik.")
else:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Gemini istemcisi başlatıldı.")
    except Exception as exc:
        logging.error(f"Gemini başlatma hatası: {exc}")

# ─────────────────────────────────────────────
# ÜRÜN VERİTABANI — uygulama başında bir kez yüklenir
# ─────────────────────────────────────────────
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB: dict = {}


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<.*?>", " ", raw)
    return re.sub(r"\s+", " ", clean).strip()


def load_product_data() -> None:
    global PERFUME_CATALOG_TEXT, PRODUCT_DB

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_FILE_NAME)

    if not os.path.exists(csv_path):
        logging.error(f"CSV bulunamadı: {csv_path}")
        PERFUME_CATALOG_TEXT = "HATA: Katalog dosyası bulunamadı."
        return

    catalog_lines = []
    temp_db = {}

    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                title = row.get("Title", "").strip()
                if not title:
                    continue

                handle = row.get("Handle", "").strip()
                body   = clean_html(row.get("Body (HTML)", ""))
                tags   = row.get("Tags", "").strip()
                image  = row.get("Image Src", "").strip()

                if handle not in temp_db:
                    temp_db[handle] = {
                        "title": title,
                        "image": image or PLACEHOLDER_IMG,
                        "url"  : f"{PRODUCT_BASE_URL}{handle}",
                    }
                    catalog_lines.append(
                        f"KİMLİK: {handle} | İSİM: {title} | ETİKETLER: {tags} | DETAY: {body[:350]}"
                    )

        PERFUME_CATALOG_TEXT = "\n".join(catalog_lines)
        PRODUCT_DB = temp_db
        logging.info(f"Katalog yüklendi — {len(PRODUCT_DB)} ürün.")

    except Exception as exc:
        logging.error(f"Katalog yükleme hatası: {exc}")
        PERFUME_CATALOG_TEXT = f"HATA: Katalog yüklenemedi. {exc}"


load_product_data()


# ─────────────────────────────────────────────
# YARDIMCI: PROMPT
# ─────────────────────────────────────────────
def build_prompt(user_query: str, has_image: bool) -> str:
    image_instruction = ""
    if has_image:
        image_instruction = """
GÖRÜNTÜ ANALİZİ REHBERİ:
Fotoğrafa bir sanatçı gözüyle bak — meslek veya üniforma etiketlerine takılma.
Bunun yerine şunları hisset:
  • Genel enerji ve atmosfer: Sakin mi, karizmatik mi, serbest ruhlu mu?
  • Renk paleti ve giyim tarzı hangi duyguyu çağrıştırıyor?
  • Klasik, bohem, minimalist, entelektüel, sportif?
  • Deri tonu: Bazı koku aileleri belirli tenlerle çok daha derin açılır.
  • Ortam enerjisi: Ev sıcaklığı mı, şehir dinamizmi mi, doğa sessizliği mi?
Kişinin RUH HALİNİ ve İÇ DÜNYASINI oku.
"""

    return (
        "Sen dünyanın en saygın parfüm butiklerinden birinde yıllarca çalışmış, "
        "koku ve insan doğasını derinden bilen bir uzmanısın.\n"
        "Müşterilere hiçbir zaman reklam gibi konuşmazsın; "
        "aksine onları gerçekten anlayan, sıcak ve biraz gizemli bir dost gibi konuşursun.\n"
        "Klişe cümleler kullanmazsın. Gözlemin ve sezginle çok özgün, kişiye özel bir şey söylersin.\n\n"
        "SARE PERFUME KATALOĞU:\n"
        + PERFUME_CATALOG_TEXT
        + "\n\n"
        + image_instruction
        + "\nGÖREVİN:\n"
        "1. Müşterinin paylaştığı metin veya fotoğrafı derinlemesine oku.\n"
        "2. Enerji, tarz, duygu ve karakterden yola çıkarak katalogdan EN UYGUN 3 parfümü seç.\n"
        "3. Her seçim için müşteriye doğrudan seslenen, 2-3 cümlelik, etkileyici ve "
        "TAMAMEN KİŞİYE ÖZEL bir açıklama yaz.\n"
        "   - Onun hakkında fark ettiğin özgün bir detaydan başla.\n"
        "   - Parfümün hangi notası o detayla neden örtüşüyor, bunu şiirsel ama sade anlat.\n"
        "   - Sonu bir gözlem veya davetle bitir, soru işaretiyle bitirme.\n\n"
        "YANIT FORMATI — SADECE GEÇERLİ JSON, başka hiçbir şey yazma:\n"
        '{"recommendations": [{"kimlik": "katalogdaki-handle", "aciklama": "2-3 cümle"}]}'
    )


# ─────────────────────────────────────────────
# YARDIMCI: KULLANICIYA ŞIK HATA
# ─────────────────────────────────────────────
USER_ERRORS = {
    "quota"  : "Koku uzmanımız şu an çok yoğun — birazdan tekrar dene.",
    "blocked": "Bu sorgu işlenemedi. Farklı bir şekilde anlatmayı dener misin?",
    "timeout": "Bağlantı zaman aşımına uğradı. Lütfen tekrar dene.",
    "default": "Beklenmedik bir sorun oluştu. Lütfen birkaç saniye sonra tekrar dene.",
}

def user_error(kind="default", status=500):
    return jsonify({"error": USER_ERRORS.get(kind, USER_ERRORS["default"])}), status


# ─────────────────────────────────────────────
# ANA ENDPOINT
# ─────────────────────────────────────────────
@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return user_error("default")

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Geçersiz istek formatı."}), 400

    user_query   = (data.get("query") or "").strip()
    image_base64 = data.get("image")

    if not user_query and not image_base64:
        return jsonify({"error": "Lütfen bir şeyler yazın veya fotoğraf yükleyin."}), 400

    has_image     = bool(image_base64)
    content_parts = [build_prompt(user_query, has_image)]

    if user_query:
        content_parts.append(f"Müşteri mesajı: {user_query}")

    if has_image:
        try:
            img_str   = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
            img_bytes = base64.b64decode(img_str)
            mime = "image/jpeg"
            if image_base64.startswith("data:image/png"):
                mime = "image/png"
            elif image_base64.startswith("data:image/webp"):
                mime = "image/webp"
            content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
        except Exception as exc:
            logging.warning(f"Resim çözümleme hatası: {exc}")
            return jsonify({"error": "Resim formatı desteklenmiyor. JPG veya PNG yükle."}), 400

    t0 = time.time()
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=content_parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.85,
                max_output_tokens=1024,
            ),
        )
        logging.info(f"Gemini yanıt: {time.time()-t0:.2f}s")

    except Exception as exc:
        err = str(exc).lower()
        logging.error(f"Gemini API hatası: {exc}")
        if "quota" in err or "429" in err:
            return user_error("quota", 429)
        if "blocked" in err:
            return user_error("blocked", 400)
        if "timeout" in err or "deadline" in err:
            return user_error("timeout", 504)
        return user_error("default")

    raw_text = ""
    try:
        raw_text = response.text.strip()
        raw_text = re.sub(r"^```(?:json)?", "", raw_text).rstrip("`").strip()
        gemini_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logging.error(f"JSON parse hatası. Ham yanıt:\n{raw_text}\nHata: {exc}")
        return user_error("default")

    final_results = []
    for rec in gemini_data.get("recommendations", []):
        handle = (rec.get("kimlik") or "").strip()
        if not handle or handle not in PRODUCT_DB:
            logging.warning(f"Bilinmeyen handle: '{handle}'")
            continue
        prod = PRODUCT_DB[handle]
        final_results.append({
            "title"      : prod["title"],
            "url"        : prod["url"],
            "image"      : prod["image"],
            "description": (rec.get("aciklama") or "").strip(),
        })

    if not final_results:
        return jsonify({"error": "Size özel bir öneri oluşturulamadı. Farklı bir şey yazar mısınız?"}), 200

    return jsonify({"recommendations": final_results})


# ─────────────────────────────────────────────
# SAĞLIK KONTROLÜ
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status"         : "ok",
        "products_loaded": len(PRODUCT_DB),
        "gemini_ready"   : client is not None,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
