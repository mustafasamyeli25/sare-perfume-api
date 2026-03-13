<!-- 
  ════════════════════════════════════════════════════════════
  SARE PERFUME — AI BUTON (TÜM SAYFALARDA)
  Eklenecek yer: theme.liquid → </body> den hemen önce
  ════════════════════════════════════════════════════════════
-->

<style>
  :root {
    --sare-gold: #c9a84c;
    --sare-dark: #1a1a2e;
    --sare-cream: #faf7f0;
    --sare-border: #ede5d0;
  }

  /* ── Floating Buton — Sol Alt ── */
  #sare-fab {
    position: fixed;
    bottom: 24px;
    left: 24px;
    z-index: 9998;
    display: flex;
    align-items: center;
    gap: 0px;
    cursor: pointer;
    border: none;
    background: none;
    padding: 0;
  }

  #sare-fab-inner {
    display: flex;
    align-items: center;
    gap: 10px;
    background: linear-gradient(135deg, #1a1a2e 0%, #2d2d4e 50%, #c9a84c 100%);
    color: #fff;
    border-radius: 50px;
    padding: 13px 20px 13px 16px;
    font-family: 'Georgia', serif;
    font-size: 13px;
    font-weight: 400;
    letter-spacing: 0.8px;
    box-shadow: 0 4px 24px rgba(26,26,46,0.35), 0 0 0 1px rgba(201,168,76,0.3);
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    white-space: nowrap;
    overflow: hidden;
    max-width: 180px;
  }

  #sare-fab:hover #sare-fab-inner {
    box-shadow: 0 6px 32px rgba(26,26,46,0.5), 0 0 0 2px rgba(201,168,76,0.6);
    transform: translateY(-3px);
    max-width: 200px;
  }

  .sare-fab-icon {
    font-size: 18px;
    flex-shrink: 0;
    animation: sare-pulse 2.5s ease-in-out infinite;
  }

  @keyframes sare-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.15); }
  }

  /* ── Modal Overlay ── */
  #sare-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(10, 10, 20, 0.7);
    z-index: 99999;
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    align-items: flex-end;
    justify-content: flex-start;
    padding: 0 0 90px 16px;
  }
  #sare-overlay.open {
    display: flex;
    animation: sare-fade-in 0.25s ease;
  }

  @keyframes sare-fade-in { from { opacity: 0; } to { opacity: 1; } }

  /* ── Modal Kutu ── */
  #sare-modal-box {
    width: 100%;
    max-width: 380px;
    background: var(--sare-cream);
    border-radius: 20px;
    border: 1px solid var(--sare-border);
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    overflow: hidden;
    animation: sare-slide-up 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  @keyframes sare-slide-up {
    from { transform: translateY(30px) scale(0.95); opacity: 0; }
    to   { transform: translateY(0) scale(1); opacity: 1; }
  }

  /* ── Modal Başlık ── */
  .sare-modal-head {
    background: linear-gradient(135deg, var(--sare-dark), #2d2d4e);
    padding: 18px 20px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sare-modal-title {
    color: #fff;
    font-family: 'Georgia', serif;
    font-size: 15px;
    letter-spacing: 0.5px;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .sare-modal-title span.gold { color: var(--sare-gold); }

  .sare-modal-close {
    background: rgba(255,255,255,0.1);
    border: none;
    color: #fff;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
  }
  .sare-modal-close:hover { background: rgba(255,255,255,0.2); }

  /* ── Modal Gövde ── */
  .sare-modal-body { padding: 18px 18px 20px; }

  /* ── Input ── */
  .sare-input-wrap {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }

  #sare-q {
    flex: 1;
    background: #fff;
    border: 1.5px solid var(--sare-border);
    border-radius: 12px;
    padding: 11px 14px;
    font-family: 'Georgia', serif;
    font-size: 13px;
    color: var(--sare-dark);
    outline: none;
    transition: border-color 0.2s;
  }
  #sare-q:focus { border-color: var(--sare-gold); }
  #sare-q::placeholder { color: #aaa; font-style: italic; }

  #sare-go {
    background: linear-gradient(135deg, var(--sare-dark), #c9a84c);
    color: #fff;
    border: none;
    border-radius: 12px;
    width: 42px;
    height: 42px;
    font-size: 16px;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  #sare-go:hover:not(:disabled) { opacity: 0.85; transform: scale(1.05); }
  #sare-go:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── Fotoğraf ── */
  .sare-photo-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
  }

  #sare-photo-btn {
    border: 1.5px dashed var(--sare-gold);
    background: rgba(201,168,76,0.06);
    color: #8a6a20;
    border-radius: 10px;
    padding: 7px 12px;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
  }
  #sare-photo-btn:hover { background: rgba(201,168,76,0.14); }
  #sare-file { display: none; }

  #sare-thumb {
    width: 44px;
    height: 44px;
    object-fit: cover;
    border-radius: 8px;
    border: 2px solid var(--sare-gold);
    display: none;
  }
  .sare-photo-hint { font-size: 11px; color: #bbb; font-style: italic; }

  /* ── Loader ── */
  .sare-loader-wrap { text-align: center; padding: 24px 0; }
  .sare-spinner {
    width: 32px; height: 32px;
    border: 3px solid var(--sare-border);
    border-top-color: var(--sare-gold);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    margin: 0 auto 10px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .sare-loader-text { font-size: 12px; color: #999; font-style: italic; font-family: 'Georgia', serif; }

  /* ── Hata ── */
  .sare-err {
    background: #fff0f0;
    color: #b03030;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 12px;
    text-align: center;
  }

  /* ── Sonuç Kartları ── */
  .sare-cards { display: flex; flex-direction: column; gap: 10px; }

  .sare-card {
    display: flex;
    gap: 12px;
    background: #fff;
    border: 1px solid var(--sare-border);
    border-radius: 14px;
    padding: 12px;
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.2s, transform 0.2s;
  }
  .sare-card:hover {
    box-shadow: 0 4px 18px rgba(201,168,76,0.2);
    transform: translateY(-1px);
  }

  .sare-card img {
    width: 60px;
    height: 60px;
    object-fit: cover;
    border-radius: 10px;
    flex-shrink: 0;
    background: var(--sare-border);
  }

  .sare-card-info { flex: 1; min-width: 0; }

  .sare-card-name {
    font-family: 'Georgia', serif;
    font-size: 13px;
    font-weight: 700;
    color: var(--sare-dark);
    margin: 0 0 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sare-card-desc {
    font-size: 11px;
    color: #666;
    line-height: 1.5;
    margin: 0 0 7px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .sare-card-link {
    display: inline-block;
    background: linear-gradient(135deg, var(--sare-dark), #c9a84c);
    color: #fff;
    font-size: 10px;
    letter-spacing: 0.5px;
    padding: 4px 10px;
    border-radius: 20px;
    font-family: 'Georgia', serif;
  }

  @media (max-width: 440px) {
    #sare-modal-box { border-radius: 16px; }
    #sare-overlay { padding: 0 8px 86px 8px; }
  }
</style>

<!-- Floating Buton -->
<button id="sare-fab" onclick="sareOpen()" aria-label="AI Koku Rehberi">
  <div id="sare-fab-inner">
    <span class="sare-fab-icon">✦</span>
    <span>Koku Bul</span>
  </div>
</button>

<!-- Modal -->
<div id="sare-overlay" onclick="sareOverlayClick(event)">
  <div id="sare-modal-box">

    <div class="sare-modal-head">
      <p class="sare-modal-title">✦ <span class="gold">Sare</span> Koku Bul</p>
      <button class="sare-modal-close" onclick="sareClose()">✕</button>
    </div>

    <div class="sare-modal-body">
      <div class="sare-input-wrap">
        <input id="sare-q" type="text" placeholder="Örn: Chanel No5, Sauvage, Black Orchid..." 
               onkeydown="if(event.key==='Enter')sareAsk()" autocomplete="off"/>
        <button id="sare-go" onclick="sareAsk()" aria-label="Gönder">➤</button>
      </div>

      <div class="sare-photo-row">
        <button id="sare-photo-btn" onclick="document.getElementById('sare-file').click()">
          📷 Fotoğraf
        </button>
        <input type="file" id="sare-file" accept="image/*" onchange="sareImg(this)"/>
        <img id="sare-thumb" alt=""/>
        <span class="sare-photo-hint" id="sare-hint">İsteğe bağlı</span>
      </div>

      <div id="sare-out"></div>
    </div>

  </div>
</div>

<script>
const SARE_API = "https://sare-perfume-api.vercel.app/recommend";
let _img = null;

function sareOpen() {
  document.getElementById('sare-overlay').classList.add('open');
  setTimeout(() => document.getElementById('sare-q').focus(), 350);
}
function sareClose() {
  document.getElementById('sare-overlay').classList.remove('open');
}
function sareOverlayClick(e) {
  if (e.target === document.getElementById('sare-overlay')) sareClose();
}

function sareImg(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    _img = e.target.result;
    const thumb = document.getElementById('sare-thumb');
    thumb.src = _img;
    thumb.style.display = 'block';
    document.getElementById('sare-hint').textContent =
      file.name.length > 18 ? file.name.slice(0,18)+'…' : file.name;
  };
  reader.readAsDataURL(file);
}

async function sareAsk() {
  const q   = document.getElementById('sare-q').value.trim();
  const btn = document.getElementById('sare-go');
  const out = document.getElementById('sare-out');

  if (!q && !_img) {
    out.innerHTML = '<div class="sare-err">Lütfen bir şeyler yazın veya fotoğraf yükleyin.</div>';
    return;
  }

  btn.disabled = true;
  out.innerHTML = `<div class="sare-loader-wrap">
    <div class="sare-spinner"></div>
    <p class="sare-loader-text">Uzman seçim yapıyor…</p>
  </div>`;

  try {
    const body = {};
    if (q)    body.query = q;
    if (_img) body.image = _img;

    const res  = await fetch(SARE_API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();

    if (data.error) {
      out.innerHTML = `<div class="sare-err">⚠️ ${data.error}</div>`;
    } else {
      out.innerHTML = '<div class="sare-cards">' +
        data.recommendations.map(r => `
          <a class="sare-card" href="${r.url}" target="_blank" rel="noopener">
            <img src="${r.image}" alt="${r.title}"
                 onerror="this.src='https://via.placeholder.com/60?text=🌸'"/>
            <div class="sare-card-info">
              <p class="sare-card-name">${r.title}</p>
              <p class="sare-card-desc">${r.description}</p>
              <span class="sare-card-link">İncele →</span>
            </div>
          </a>`).join('') +
        '</div>';
    }
  } catch(e) {
    out.innerHTML = '<div class="sare-err">⚠️ Bağlantı hatası. Tekrar dene.</div>';
  } finally {
    btn.disabled = false;
  }
}
</script>
