"""
Sare Perfume - AI Danışman Backend
FastAPI + Pinecone (RAG) + Redis Cache + Groq/Gemini LLM + Gemini Vision
Vercel deployment ready
"""

import os
import json
import base64
import hashlib
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Environment Variables ─────────────────────────────────────────────────────
# Hepsi .get() ile alınıyor — eksik variable app'i başlatma aşamasında çökertemez.
# Endpoint çağrısında eksikse anlamlı hata mesajı döner.
PINECONE_API_KEY    = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX      = os.environ.get("PINECONE_INDEX", "sare-perfume")
PINECONE_HOST       = os.environ.get("PINECONE_HOST", "")   # https://sare-perfume-xxxx.svc.xxx.pinecone.io

UPSTASH_REDIS_URL   = os.environ.get("UPSTASH_REDIS_URL", "")
UPSTASH_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_TOKEN", "")

GEMINI_API_KEYS     = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()]
GROQ_API_KEYS       = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]

CACHE_TTL          = int(os.environ.get("CACHE_TTL", 3600))   # seconds
TOP_K              = int(os.environ.get("TOP_K", 3))

# ── Key Rotation State ────────────────────────────────────────────────────────
_groq_idx   = 0
_gemini_idx = 0

def next_groq_key() -> str:
    global _groq_idx
    if not GROQ_API_KEYS:
        raise ValueError("GROQ_API_KEYS boş!")
    key = GROQ_API_KEYS[_groq_idx % len(GROQ_API_KEYS)]
    _groq_idx += 1
    return key

def next_gemini_key() -> str:
    global _gemini_idx
    if not GEMINI_API_KEYS:
        raise ValueError("GEMINI_API_KEYS boş!")
    key = GEMINI_API_KEYS[_gemini_idx % len(GEMINI_API_KEYS)]
    _gemini_idx += 1
    return key

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Sare Perfume AI Danışman başlatılıyor...")
    yield
    logger.info("🛑 Uygulama kapatılıyor.")

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Sare Perfume AI Danışman",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Shopify domain'ini buraya ekleyebilirsin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response Models ─────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    gender: Optional[str] = None       # "erkek" | "kadın" | "unisex"
    season: Optional[str] = None       # "yaz" | "kış" | "ilkbahar" | "sonbahar"
    budget: Optional[str] = None       # "düşük" | "orta" | "yüksek"
    occasion: Optional[str] = None     # "iş" | "gece" | "günlük" | "özel"


class Recommendation(BaseModel):
    title: str
    url: str
    image: str
    description: str
    price: Optional[str] = None
    score: Optional[float] = None


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    message: str
    cached: bool = False


# ══════════════════════════════════════════════════════════════════════════════
# REDIS CACHE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def make_cache_key(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return "sare:" + hashlib.sha256(raw.encode()).hexdigest()[:24]

async def redis_get(key: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(
                f"{UPSTASH_REDIS_URL}/get/{key}",
                headers={"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}"},
            )
            data = r.json()
            return data.get("result")
    except Exception as e:
        logger.warning(f"Redis GET hatası: {e}")
        return None

async def redis_set(key: str, value: str, ttl: int = CACHE_TTL) -> None:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(
                f"{UPSTASH_REDIS_URL}/set/{key}",
                headers={
                    "Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"value": value, "ex": ttl},
            )
    except Exception as e:
        logger.warning(f"Redis SET hatası: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

async def embed_text(text: str) -> list[float]:
    """Gemini text-embedding-004 ile 768 boyutlu vektör üret."""
    api_key = next_gemini_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"text-embedding-004:embedContent?key={api_key}"
    )
    payload = {
        "model": "models/text-embedding-004",
        "content": {"parts": [{"text": text}]},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()["embedding"]["values"]


# ══════════════════════════════════════════════════════════════════════════════
# PINECONE QUERY
# ══════════════════════════════════════════════════════════════════════════════

async def pinecone_query(vector: list[float], top_k: int = TOP_K, filter_meta: dict = None) -> list[dict]:
    """Pinecone'da en yakın parfümleri bul."""
    payload: dict = {
        "vector": vector,
        "topK": top_k,
        "includeMetadata": True,
    }
    if filter_meta:
        payload["filter"] = filter_meta

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{PINECONE_HOST}/query",
            headers={
                "Api-Key": PINECONE_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        matches = r.json().get("matches", [])

    results = []
    for m in matches:
        meta = m.get("metadata", {})
        results.append({
            "id": m.get("id"),
            "score": round(m.get("score", 0), 4),
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
            "image": meta.get("image", ""),
            "price": meta.get("price", ""),
            "notes": meta.get("notes", ""),
            "season": meta.get("season", ""),
            "gender": meta.get("gender", ""),
            "description": meta.get("description", ""),
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
# LLM: GROQ (Ana) + GEMINI FLASH (Fallback)
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt() -> str:
    return """Sen Sare Perfume'ün uzman parfüm danışmanısın. 
Müşterilere sıcak, zarif ve kişisel bir deneyim sunarsın.
Görevin: Sana verilen ürün listesinden müşteriye en uygun parfümleri seçmek ve 
her biri için büyüleyici, duygusal bir pazarlama açıklaması yazmak.

KURALLAR:
- Mutlaka JSON formatında yanıt ver (başka hiçbir şey yazma)
- Her parfüm için 2-3 cümlelik etkileyici Türkçe açıklama yaz
- Müşterinin tercihlerini (mevsim, cinsiyet, bütçe, ortam) mutlaka göz önünde bulundur
- Samimi ve lüks bir dil kullan

YANIT FORMATI (kesinlikle bu JSON):
{
  "message": "Müşteriye özel samimi bir karşılama mesajı (1-2 cümle)",
  "recommendations": [
    {
      "title": "Parfüm Adı",
      "url": "ürün linki",
      "image": "resim url",
      "price": "fiyat",
      "description": "2-3 cümle büyüleyici açıklama"
    }
  ]
}"""

def build_user_prompt(query: str, products: list[dict], filters: dict) -> str:
    filter_text = ""
    if filters.get("gender"):
        filter_text += f"Cinsiyet tercihi: {filters['gender']}\n"
    if filters.get("season"):
        filter_text += f"Mevsim: {filters['season']}\n"
    if filters.get("budget"):
        filter_text += f"Bütçe: {filters['budget']}\n"
    if filters.get("occasion"):
        filter_text += f"Kullanım ortamı: {filters['occasion']}\n"

    products_text = ""
    for i, p in enumerate(products, 1):
        products_text += f"""
Ürün {i}:
- İsim: {p['title']}
- URL: {p['url']}
- Resim: {p['image']}
- Fiyat: {p.get('price', 'Belirtilmemiş')}
- Notalar: {p.get('notes', '')}
- Mevsim: {p.get('season', '')}
- Cinsiyet: {p.get('gender', '')}
- Açıklama: {p.get('description', '')}
"""

    return f"""Müşteri isteği: "{query}"

{filter_text}
Aşağıdaki parfümler arasından en uygun olanları öner:
{products_text}

Lütfen JSON formatında yanıt ver."""


async def call_groq(system: str, user: str) -> dict:
    """Groq Llama-3.3-70b ile LLM çağrısı."""
    api_key = next_groq_key()
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)


async def call_gemini_flash(system: str, user: str) -> dict:
    """Gemini 2.0 Flash fallback."""
    api_key = next_gemini_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1500,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


async def call_llm(system: str, user: str) -> dict:
    """Groq dene, başarısız olursa Gemini Flash'a geç."""
    try:
        logger.info("🤖 Groq çağrılıyor...")
        return await call_groq(system, user)
    except Exception as e:
        logger.warning(f"Groq hatası ({e}), Gemini Flash'a geçiliyor...")
        return await call_gemini_flash(system, user)


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI VISION - Stil Analizi
# ══════════════════════════════════════════════════════════════════════════════

async def analyze_style_with_vision(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Müşterinin kıyafet/stil fotoğrafını analiz et, parfüm önerisi için bağlam üret."""
    api_key = next_gemini_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    image_b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                    {
                        "text": (
                            "Bu fotoğraftaki kişinin stilini, ruh halini ve genel estetik duruşunu analiz et. "
                            "Renk paleti, giyim tarzı ve atmosferi göz önünde bulundurarak bu kişiye uygun parfüm "
                            "notalarını ve özelliklerini Türkçe olarak kısa ve öz bir şekilde belirt. "
                            "Sadece parfüm arama sorgusuna dönüştürülebilecek bir metin yaz."
                        )
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 300},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# CORE RAG PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

async def rag_pipeline(query: str, filters: dict) -> dict:
    """
    1. Redis kontrol
    2. Embedding
    3. Pinecone sorgu
    4. LLM (Groq / Gemini fallback)
    5. Redis'e kaydet
    """
    cache_key = make_cache_key({"q": query, **filters})

    # 1. Cache kontrolü
    cached = await redis_get(cache_key)
    if cached:
        logger.info(f"✅ Cache hit: {cache_key}")
        result = json.loads(cached)
        result["cached"] = True
        return result

    # 2. Embedding
    logger.info("🔢 Embedding oluşturuluyor...")
    vector = await embed_text(query)

    # 3. Pinecone – opsiyonel metadata filtresi
    pinecone_filter = {}
    if filters.get("gender"):
        pinecone_filter["gender"] = {"$in": [filters["gender"], "unisex"]}
    if filters.get("season"):
        pinecone_filter["season"] = {"$in": [filters["season"], "tüm mevsimler"]}

    logger.info("📌 Pinecone sorgulanıyor...")
    products = await pinecone_query(vector, top_k=TOP_K, filter_meta=pinecone_filter or None)

    if not products:
        raise HTTPException(status_code=404, detail="Uygun parfüm bulunamadı.")

    # 4. LLM
    logger.info("✨ LLM çağrılıyor...")
    system_prompt = build_system_prompt()
    user_prompt   = build_user_prompt(query, products, filters)
    llm_response  = await call_llm(system_prompt, user_prompt)

    # LLM çıktısını normalize et
    recommendations = []
    for item in llm_response.get("recommendations", []):
        recommendations.append(Recommendation(
            title=item.get("title", ""),
            url=item.get("url", ""),
            image=item.get("image", ""),
            description=item.get("description", ""),
            price=item.get("price"),
        ).model_dump())

    result = {
        "recommendations": recommendations,
        "message": llm_response.get("message", "Size özel parfüm önerilerim hazır!"),
        "cached": False,
    }

    # 5. Cache'e kaydet
    await redis_set(cache_key, json.dumps(result, ensure_ascii=False))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "ok", "service": "Sare Perfume AI Danışman v2.0"}


@app.get("/health")
async def health():
    missing = []
    if not PINECONE_API_KEY:    missing.append("PINECONE_API_KEY")
    if not PINECONE_HOST:       missing.append("PINECONE_HOST")
    if not UPSTASH_REDIS_URL:   missing.append("UPSTASH_REDIS_URL")
    if not UPSTASH_REDIS_TOKEN: missing.append("UPSTASH_REDIS_TOKEN")
    if not GEMINI_API_KEYS:     missing.append("GEMINI_API_KEYS")
    if not GROQ_API_KEYS:       missing.append("GROQ_API_KEYS")
    return {
        "status": "healthy" if not missing else "degraded",
        "missing_env_vars": missing,
        "pinecone_index": PINECONE_INDEX,
        "pinecone_host_set": bool(PINECONE_HOST),
        "groq_keys": len(GROQ_API_KEYS),
        "gemini_keys": len(GEMINI_API_KEYS),
    }


@app.post("/recommend", response_model=RecommendationResponse)
async def recommend(req: QueryRequest):
    """
    Ana öneri endpoint'i.
    Shopify frontend'den fetch ile çağrılır.
    """
    if not req.query or len(req.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Lütfen geçerli bir sorgu girin.")

    filters = {
        "gender": req.gender,
        "season": req.season,
        "budget": req.budget,
        "occasion": req.occasion,
    }
    # None değerleri temizle
    filters = {k: v for k, v in filters.items() if v}

    result = await rag_pipeline(req.query, filters)
    return JSONResponse(content=result)


@app.post("/recommend-by-image", response_model=RecommendationResponse)
async def recommend_by_image(
    image: UploadFile = File(...),
    gender: Optional[str] = Form(None),
    season: Optional[str] = Form(None),
    budget: Optional[str] = Form(None),
    occasion: Optional[str] = Form(None),
):
    """
    Müşteri fotoğraf yükler -> Gemini Vision stil analizi -> RAG pipeline.
    """
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Sadece JPEG, PNG veya WebP yükleyebilirsiniz.")

    image_bytes = await image.read()
    if len(image_bytes) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(status_code=400, detail="Resim boyutu 5 MB'ı geçemez.")

    logger.info("🖼️ Görsel analiz ediliyor...")
    style_query = await analyze_style_with_vision(image_bytes, image.content_type)
    logger.info(f"Stil analizi: {style_query}")

    filters = {k: v for k, v in {
        "gender": gender, "season": season,
        "budget": budget, "occasion": occasion,
    }.items() if v}

    result = await rag_pipeline(style_query, filters)
    result["style_analysis"] = style_query   # Frontend'e bonus bilgi
    return JSONResponse(content=result)


@app.post("/search")
async def search(req: QueryRequest):
    """
    Doğrudan Pinecone vektör araması (LLM olmadan, hız gerektiren durumlar için).
    """
    vector   = await embed_text(req.query)
    products = await pinecone_query(vector, top_k=6)
    return JSONResponse(content={"results": products})


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL DEV
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
