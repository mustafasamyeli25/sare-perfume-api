import os, json, random, logging, time, re, base64
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
import google.generativeai as genai
from pinecone import Pinecone
from upstash_redis import Redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

app = FastAPI()

# Shopify frontend'in API ile konuşabilmesi için CORS izni
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. DIŞ SERVİS BAĞLANTILARI
# ==========================================
PINECONE_KEY = os.environ.get("PINECONE_API_KEY", "")
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# Pinecone ve Redis'i Başlat
pc = Pinecone(api_key=PINECONE_KEY) if PINECONE_KEY else None
index = pc.Index("sare-perfume") if pc else None
redis = Redis(url=REDIS_URL, token=REDIS_TOKEN) if REDIS_URL and REDIS_TOKEN else None

# ==========================================
# 2. ÇOKLU API ANAHTARI YÖNETİMİ
# ==========================================
def get_keys(prefix):
    """Vercel'den virgülle ayrılmış veya _1, _2 formatındaki anahtarları toplar."""
    keys = []
    val = os.environ.get(prefix, "").strip()
    if val:
        keys.extend([k.strip() for k in val.split(",") if k.strip()])
    for i in range(1, 15):
        k = os.environ.get(f"{prefix}_{i}", "").strip()
        if k: keys.append(k)
    return list(dict.fromkeys(keys))

GROQ_KEYS = get_keys("GROQ_API_KEY")
GEMINI_KEYS = get_keys("GEMINI_API_KEY")

if GEMINI_KEYS:
    # Varsayılan olarak ilk Gemini anahtarını kütüphaneye tanımlayalım
    genai.configure(api_key=GEMINI_KEYS[0])

GROQ_INDEX = 0

# ==========================================
# 3. YARDIMCI YAPAY ZEKA FONKSİYONLARI
# ==========================================
def get_embedding(text: str):
    """Müşterinin sorusunu Pinecone'un arayacağı 768 boyutlu vektöre çevirir."""
    models = genai.list_models()
    embed_model = next((m.name for m in models if 'embedContent' in m.supported_generation_methods), "models/embedding-001")
    resp = genai.embed_content(model=embed_model, content=text, task_type="retrieval_query")
    return resp['embedding'][:768] 

def analyze_image_with_gemini(image_b64: str) -> str:
    """Müşterinin yüklediği fotoğrafı analiz edip, tarzını/enerjisini metne döker."""
    img_str = image_b64.split(",", 1)[-1] if "," in image_b64 else image_b64
    mime = "image/jpeg"
    if image_base64.startswith("data:image/png"): mime = "image/png"
    elif image_base64.startswith("data:image/webp"): mime = "image/webp"
    
    # Gemini'nin görme (vision) yetenekli modelini kullanıyoruz
    model = genai.GenerativeModel('gemini-2.0-flash') 
    prompt = "Bu fotoğraftaki kişinin genel tarzını, enerjisini, renk paletini ve ortam atmosferini oku. Ona en uygun parfümü seçmek için bana 1-2 cümlelik bir stil özeti çıkar."
    
    response = model.generate_content([
        prompt, 
        {"mime_type": mime, "data": img_str}
    ])
    return response.text

def call_groq(prompt: str):
    """Birincil Yapay Zeka (Groq LLaMA 3) - Çoklu Anahtar ile."""
    global GROQ_INDEX
    if not GROQ_KEYS: raise Exception("Groq anahtarı yok.")
    
    n = len(GROQ_KEYS)
    keys_to_try = [GROQ_KEYS[(GROQ_INDEX + i) % n] for i in range(n)]
    GROQ_INDEX = (GROQ_INDEX + 1) % n

    for key in keys_to_try:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7
                },
                timeout=15
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            elif r.status_code == 429: 
                time.sleep(1)
                continue
        except: continue
    raise Exception("Tüm Groq anahtarları başarısız oldu.")

def call_gemini_fallback(prompt: str):
    """Yedek Yapay Zeka (Gemini) - Groq çökerse devreye girer."""
    keys_to_try = GEMINI_KEYS.copy()
    random.shuffle(keys_to_try) 
    
    for key in keys_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            r = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"} 
            }, timeout=15)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except: continue
    raise Exception("Gemini de başarısız oldu.")

# ==========================================
# 4. ANA API ENDPOINT (Müşteri buraya istek atar)
# ==========================================
@app.post("/recommend")
async def recommend(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Geçersiz istek."}, status_code=400)

    user_query = data.get("query", "").strip()
    image_base64 = data.get("image")

    if not user_query and not image_base64:
        return JSONResponse({"error": "Lütfen bir koku tarzı yazın veya fotoğraf yükleyin."}, status_code=400)

    image_context = ""
    # EĞER FOTOĞRAF VARSA ÖNCE ONU ANALİZ ET
    if image_base64:
        try:
            image_context = analyze_image_with_gemini(image_base64)
            logging.info(f"📸 Resim analizi tamamlandı: {image_context}")
        except Exception as e:
            logging.warning(f"Resim analizi başarısız: {e}")
            return JSONResponse({"error": "Fotoğraf analiz edilemedi, lütfen farklı bir fotoğraf deneyin."}, status_code=400)

    # Arama metnini birleştir
    combined_search_text = f"{user_query} {image_context}".strip()

    # ADIM 1: ÖN BELLEK (REDİS)
    cache_key = f"sare_query:{combined_search_text.lower()}"
    if redis:
        try:
            cached_result = redis.get(cache_key)
            if cached_result:
                logging.info("⚡ Redis'ten önbellek yanıtı döndü.")
                res_str = cached_result.decode("utf-8") if isinstance(cached_result, bytes) else cached_result
                return JSONResponse(json.loads(res_str))
        except Exception as e:
            logging.warning(f"Redis hatası: {e}")

    # ADIM 2: SEMANTİK ARAMA (PINECONE)
    try:
        query_vector = get_embedding(combined_search_text)
        search_results = index.query(vector=query_vector, top_k=3, include_metadata=True)
    except Exception as e:
        logging.error(f"Pinecone Arama Hatası: {e}")
        return JSONResponse({"error": "Veritabanına ulaşılamadı. Lütfen tekrar deneyin."}, status_code=500)

    context_text = ""
    products_db = []
    
    for match in search_results.get("matches", []):
        md = match.get("metadata", {})
        handle = md.get("handle", "bilinmeyen")
        title = md.get("title", "Parfüm")
        desc = md.get("text", "")
        
        context_text += f"- Ürün ID: {handle} | İsim: {title} | Özellikler: {desc}\n"
        products_db.append({
            "handle": handle,
            "title": title,
            "image": md.get("image", "https://via.placeholder.com/150?text=Sare+Perfume"),
            "url": f"https://sareperfume.com/products/{handle}"
        })

    # ADIM 3: YAPAY ZEKAYA (LLM) GİDECEK PROMPT
    prompt = f"""
    Sen Sare Parfüm'ün uzman danışmanısın.
    
    Müşterinin Mesajı: "{user_query}"
    Müşterinin Fotoğraf Analizi (Eğer varsa): "{image_context}"
    
    Veritabanımızdan müşterinin aradığına en uygun şu 3 ürünü bulduk:
    {context_text}
    
    GÖREV: Bu 3 parfümü müşteriye zarif, edebi ve kokuyu hissettirecek bir dille anlat.
    - SADECE JSON formatında çıktı ver. Başka hiçbir şey yazma.
    - Orijinal markalardan bahsederken "ilham alan" gibi şık tabirler kullan.
    
    FORMAT ŞÖYLE OLMALI:
    {{
      "recommendations": [
        {{
          "kimlik": "urun-id-buraya",
          "aciklama": "Parfümün 2-3 cümlelik şık ve cezbedici anlatımı."
        }}
      ]
    }}
    """

    # ADIM 4: YANIT ÜRET VE KULLANICIYA GÖNDER
    raw_json = None
    try:
        raw_json = call_groq(prompt)
        logging.info("🚀 Groq ile başarıyla yanıt üretildi.")
    except Exception as e:
        logging.warning(f"Groq çöktü, Gemini'ye geçiliyor: {e}")
        try:
            raw_json = call_gemini_fallback(prompt)
            logging.info("⭐ Gemini ile başarıyla yedek yanıt üretildi.")
        except Exception as err:
            logging.error(f"Her iki API de çöktü: {err}")
            return JSONResponse({"error": "Danışmanlarımız çok meşgul. Lütfen birazdan tekrar deneyin."}, status_code=503)

    try:
        # JSON temizleme ve parse etme
        cleaned_json = re.sub(r'^
