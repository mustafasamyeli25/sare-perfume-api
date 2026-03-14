"""
Sare Perfume - AI Danışman Backend v4
Rüya Takımı:
- Embedding: Cohere (embed-multilingual-v3.0, 1024 dim)
- LLM: Groq (llama-3.3-70b) → Gemini fallback
- Vision: Gemini Flash
- Cache: Upstash Redis
- Arama: Pinecone SDK
"""

import os
import json
import base64
import hashlib
import logging
import unicodedata
import re
from itertools import cycle
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import cohere
import google.generativeai as genai
from pinecone import Pinecone
from groq import Groq
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Env Variables ─────────────────────────────────────────────────────────────
COHERE_API_KEY      = os.environ.get("COHERE_API_KEY", "")
PINECONE_API_KEY    = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX", "sare-perfume-cohere")

UPSTASH_REDIS_URL   = (os.environ.get("UPSTASH_REDIS_URL") or
                       os.environ.get("UPSTASH_REDIS_REST_URL", ""))
UPSTASH_REDIS_TOKEN = (os.environ.get("UPSTASH_REDIS_TOKEN") or
                       os.environ.get("UPSTASH_REDIS_REST_TOKEN", ""))

_gemini_raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY", "")
GEMINI_KEYS = [k.strip() for k in _gemini_raw.split(",") if k.strip()]

_groq_raw = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _groq_raw.split(",") if k.strip()]

CACHE_TTL    = int(os.environ.get("CACHE_TTL", 3600))
TOP_K        = int(os.environ.get("TOP_K", 3))
COHERE_DIM   = 1024

# ── Key Rotasyonu ─────────────────────────────────────────────────────────────
_gem_cycle  = None
_groq_cycle = None

def get_gemini_key() -> str:
    global _gem_cycle
    if not GEMINI_KEYS:
        raise HTTPException(503, "GEMINI_API_KEY tanimli degil")
    if _gem_cycle is None:
        _gem_cycle = cycle(GEMINI_KEYS)
    return next(_gem_cycle)

def get_groq_key() -> str:
    global _groq_cycle
    if not GROQ_KEYS:
        raise HTTPException(503, "GROQ_API_KEY tanimli degil")
    if _groq_cycle is None:
        _groq_cycle = cycle(GROQ_KEYS)
    return next(_groq_cycle)

# ── Pinecone SDK ──────────────────────────────────────────────────────────────
_pc_index = None

def get_index():
    global _pc_index
    if _pc_index is None:
        if not PINECONE_API_KEY:
            raise HTTPException(503, "PINECONE_API_KEY tanimli degil")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pc_index = pc.Index(PINECONE_INDEX_NAME)
        logger.info(f"Pinecone baglandi: {PINECONE_INDEX_NAME}")
    return _pc_index

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Sare Perfume AI v4", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query:    Optional[str] = None
    image:    Optional[str] = None
    gender:   Optional[str] = None
    season:   Optional[str] = None
    budget:   Optional[str] = None
    occasion: Optional[str] = None

class Recommendation(BaseModel):
    title:       str
    url:         str
    image:       str
    description: str
    price:       Optional[str] = None

class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    message: str
    cached:  bool = False

# ── Redis Cache ───────────────────────────────────────────────────────────────
def _redis_ok() -> bool:
    return (bool(UPSTASH_REDIS_URL) and
            UPSTASH_REDIS_URL.startswith("https://") and
            bool(UPSTASH_REDIS_TOKEN))

def _cache_key(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return "sare:" + hashlib.sha256(raw.encode()).hexdigest()[:24]

async def cache_get(key: str) -> Optional[str]:
    if not _redis_ok():
        return None
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(
                f"{UPSTASH_REDIS_URL}/get/{key}",
                headers={"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}"},
            )
            return r.json().get("result")
    except Exception as e:
        logger.warning(f"Cache GET: {e}")
        return None

async def cache_set(key: str, value: str) -> None:
    if not _redis_ok():
        return
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            await c.post(
                f"{UPSTASH_REDIS_URL}/set/{key}",
                headers={"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}",
                         "Content-Type": "application/json"},
                json={"value": value, "ex": CACHE_TTL},
            )
    except Exception as e:
        logger.warning(f"Cache SET: {e}")

# ── Embedding — Cohere ────────────────────────────────────────────────────────
def embed_text_sync(text: str) -> list[float]:
    """
    Cohere embed-multilingual-v3.0 ile 1024 boyutlu vektör üret.
    Pinecone'a yüklerken search_document, aramada search_query kullanılır.
    """
    if not COHERE_API_KEY:
        raise HTTPException(503, "COHERE_API_KEY tanimli degil")
    try:
        co = cohere.Client(COHERE_API_KEY)
        response = co.embed(
            texts=[text],
            model="embed-multilingual-v3.0",
            input_type="search_query",
        )
        values = response.embeddings[0]
        logger.info(f"Cohere embedding OK: {len(values)} dim")
        return values
    except Exception as e:
        raise HTTPException(503, f"Cohere embedding basarisiz: {e}")

# ── ID normalize (Pinecone ASCII zorunluluğu) ─────────────────────────────────
def ascii_id(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9-]', '-', text.lower())
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:100]

# ── Pinecone Arama ────────────────────────────────────────────────────────────
def pinecone_search(vector: list[float], filter_meta: dict = None) -> list[dict]:
    kwargs = {"vector": vector, "top_k": TOP_K, "include_metadata": True}
    if filter_meta:
        kwargs["filter"] = filter_meta
    resp = get_index().query(**kwargs)
    results = []
    for m in resp.matches:
        meta = m.metadata or {}
        results.append({
            "score":       round(m.score, 4),
            "title":       meta.get("title", ""),
            "url":         meta.get("url", ""),
            "image":       meta.get("image", ""),
            "price":       meta.get("price", ""),
            "notes":       meta.get("notes", ""),
            "season":      meta.get("season", ""),
            "gender":      meta.get("gender", ""),
            "description": meta.get("description", ""),
        })
    return results

# ── LLM — Groq ana + Gemini fallback ─────────────────────────────────────────
SYSTEM_PROMPT = """Sen Sare Perfume'un parfüm danışmanısın. Amacın müşteriyi o kokuya aşık etmek.

Görevin: Verilen ürünler arasından en uygunları seç ve her biri için büyüleyici bir açıklama yaz.

AÇIKLAMA KURALLARI — KESİNLİKLE UY:
1. Müşteriyi bir sahneye, bir ana, bir hisse götür. Gözlerini kapatıp o kokuyu neredeymiş gibi hayal etsin.
   Örnek: "Gözlerini kapat. Issız bir ormanın içindesin, çam kokuları, kuş cıvıltıları... İşte bu parfüm tam olarak bu."
   Örnek: "Sabahın erken saatleri, deniz kenarında kahve içiyorsun, tuzlu esinti yüzüne vuruyor. Bu koku o anı yaşatıyor."

2. Eğer müşteri yaşını, cinsiyetini belirttiyse veya fotoğraf yüklediyse — onu o sahneye KOY:
   Örnek (genç kadın): "Genç ve özgür enerjin bu kokuyla mükemmel uyum sağlıyor — tıpkı sen gibi taze, cesur ve unutulmaz."
   Örnek (olgun erkek): "Deneyimli ve özgüvenli duruşun bu derin kokuyla taçlanıyor."

3. Son cümle merak uyandırsın, satın almaya itsин:
   Örnek: "Bir kez deneyenler bir daha bırakamıyor."
   Örnek: "Çevrenizdekiler mutlaka soracak."

YASAKLAR:
- ASLA "Bu parfüm X markasından ilham almıştır" yazma
- ASLA rakip marka ismi kullanma (Chanel, Dior, YSL, Versace vb.)
- ASLA kuru ve teknik açıklama yapma
- ASLA klişe reklam dili ("benzersiz", "özel formül" gibi)

YALNIZCA şu JSON formatında yanıt ver:
{
  "message": "Müşteriye özel, onu öven ve merak uyandıran 1-2 cümle karşılama",
  "recommendations": [
    {"title": "...", "url": "...", "image": "...", "price": "...", "description": "..."}
  ]
}"""

def build_prompt(query: str, products: list[dict], filters: dict) -> str:
    musteri = f'Müşteri isteği: "{query}"\n'
    if filters.get("gender"):
        g = {"erkek": "Erkek müşteri", "kadin": "Kadın müşteri", "uniseks": "Unisex tercih"}.get(filters["gender"], filters["gender"])
        musteri += f"Cinsiyet: {g}\n"
    if filters.get("season"):
        musteri += f"Mevsim: {filters['season']}\n"
    if filters.get("occasion"):
        musteri += f"Kullanım: {filters['occasion']}\n"
    if filters.get("budget"):
        musteri += f"Bütçe: {filters['budget']}\n"
    plines = ""
    for i, p in enumerate(products, 1):
        plines += (f"\nÜrün {i}: {p['title']}\n"
                   f"  URL: {p['url']} | Resim: {p['image']} | Fiyat: {p.get('price','—')}\n"
                   f"  Notalar: {p.get('notes','—')} | Mevsim: {p.get('season','—')} | Cinsiyet: {p.get('gender','—')}\n"
                   f"  Açıklama: {p.get('description','—')}\n")
    return f'{musteri}\nÜrünler:{plines}\nJSON formatında yanıt ver.'

def call_groq_sync(prompt: str) -> dict:
    last_err = None
    for _ in range(len(GROQ_KEYS)):
        try:
            client = Groq(api_key=get_groq_key())
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user",   "content": prompt}],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            last_err = str(e)
            logger.warning(f"Groq hatasi: {e}")
    raise Exception(f"Tum Groq keyleri basarisiz: {last_err}")

def call_gemini_sync(prompt: str) -> dict:
    last_err = None
    for _ in range(len(GEMINI_KEYS)):
        try:
            genai.configure(api_key=get_gemini_key())
            model = genai.GenerativeModel(
                "gemini-2.0-flash",
                system_instruction=SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=1500,
                    response_mime_type="application/json",
                ),
            )
            resp = model.generate_content(prompt)
            return json.loads(resp.text)
        except Exception as e:
            last_err = str(e)
            logger.warning(f"Gemini LLM hatasi: {e}")
    raise Exception(f"Tum Gemini keyleri basarisiz: {last_err}")

def call_llm_sync(prompt: str) -> dict:
    try:
        logger.info("Groq cagiriliyor...")
        return call_groq_sync(prompt)
    except Exception as e:
        logger.warning(f"Groq basarisiz ({e}), Gemini'ye geciliyor...")
        return call_gemini_sync(prompt)

# ── Vision — Gemini Flash ─────────────────────────────────────────────────────
def analyze_style_sync(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    last_err = None
    for _ in range(len(GEMINI_KEYS)):
        try:
            genai.configure(api_key=get_gemini_key())
            model = genai.GenerativeModel("gemini-2.0-flash")
            prompt = (
                "Bu fotograftaki kisinin stilini analiz et. "
                "Renk paleti, giyim tarzi ve atmosferi goz onunde bulundurarak "
                "bu kisiye uygun parfum notalarini Turkce olarak belirt. "
                "Sadece parfum arama sorgusuna donusturulebilecek bir metin yaz, maks 20 kelime."
            )
            resp = model.generate_content([{"mime_type": mime_type, "data": image_bytes}, prompt])
            return resp.text.strip()
        except Exception as e:
            last_err = str(e)
            logger.warning(f"Vision hatasi: {e}")
    raise HTTPException(503, f"Vision basarisiz: {last_err}")

# ── RAG Pipeline ──────────────────────────────────────────────────────────────
async def rag_pipeline(query: str, filters: dict) -> dict:
    import asyncio
    loop = asyncio.get_event_loop()

    # Cache
    ck = _cache_key({"q": query, **filters})
    hit = await cache_get(ck)
    if hit:
        data = json.loads(hit)
        data["cached"] = True
        return data

    # Cohere Embedding
    vector = await loop.run_in_executor(None, embed_text_sync, query)

    # Pinecone filtresi
    pf = {}
    if filters.get("gender"):
        pf["gender"] = {"$in": [filters["gender"], "uniseks"]}
    if filters.get("season"):
        pf["season"] = {"$in": [filters["season"], "tum mevsimler"]}

    products = await loop.run_in_executor(None, pinecone_search, vector, pf or None)
    if not products:
        raise HTTPException(404, "Uygun parfum bulunamadi.")

    # LLM
    prompt = build_prompt(query, products, filters)
    llm    = await loop.run_in_executor(None, call_llm_sync, prompt)

    recs = [
        Recommendation(
            title=r.get("title", ""),
            url=r.get("url", ""),
            image=r.get("image", ""),
            description=r.get("description", ""),
            price=r.get("price"),
        ).model_dump()
        for r in llm.get("recommendations", [])
    ]

    result = {
        "recommendations": recs,
        "message": llm.get("message", "Size ozel parfum onerilerim hazir!"),
        "cached": False,
    }
    await cache_set(ck, json.dumps(result, ensure_ascii=False))
    return result

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "service": "Sare Perfume AI v4 — Rüya Takımı"}

@app.get("/health")
async def health():
    missing = []
    if not COHERE_API_KEY:   missing.append("COHERE_API_KEY")
    if not PINECONE_API_KEY: missing.append("PINECONE_API_KEY")
    if not GEMINI_KEYS:      missing.append("GEMINI_API_KEY(S)")
    if not GROQ_KEYS:        missing.append("GROQ_API_KEY(S)")
    return {
        "status":         "healthy" if not missing else "degraded",
        "missing":        missing,
        "cohere":         bool(COHERE_API_KEY),
        "gemini_keys":    len(GEMINI_KEYS),
        "groq_keys":      len(GROQ_KEYS),
        "redis_ready":    _redis_ok(),
        "pinecone_index": PINECONE_INDEX_NAME,
    }

@app.post("/recommend", response_model=RecommendationResponse)
async def recommend(req: QueryRequest):
    import asyncio
    loop = asyncio.get_event_loop()
    filters = {k: v for k, v in {
        "gender": req.gender, "season": req.season,
        "budget": req.budget, "occasion": req.occasion,
    }.items() if v}

    if req.image:
        try:
            header, b64data = req.image.split(",", 1)
            mime = header.split(":")[1].split(";")[0]
            img_bytes = base64.b64decode(b64data)
            query = await loop.run_in_executor(None, analyze_style_sync, img_bytes, mime)
            logger.info(f"Vision sorgusu: {query}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Gorsel islenemedi: {e}")
    elif req.query and len(req.query.strip()) >= 2:
        query = req.query.strip()
    else:
        raise HTTPException(400, "Lutfen metin yazin veya fotograf yukleyin.")

    result = await rag_pipeline(query, filters)
    return JSONResponse(content=result)

@app.post("/recommend-by-image", response_model=RecommendationResponse)
async def recommend_by_image(
    image:    UploadFile = File(...),
    gender:   Optional[str] = Form(None),
    season:   Optional[str] = Form(None),
    budget:   Optional[str] = Form(None),
    occasion: Optional[str] = Form(None),
):
    import asyncio
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(400, "Sadece JPEG, PNG veya WebP yukleyebilirsiniz.")
    img_bytes = await image.read()
    if len(img_bytes) > 5 * 1024 * 1024:
        raise HTTPException(400, "Resim 5 MB'i gecemez.")
    loop = asyncio.get_event_loop()
    query = await loop.run_in_executor(None, analyze_style_sync, img_bytes, image.content_type)
    filters = {k: v for k, v in {
        "gender": gender, "season": season,
        "budget": budget, "occasion": occasion,
    }.items() if v}
    result = await rag_pipeline(query, filters)
    result["style_analysis"] = query
    return JSONResponse(content=result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
