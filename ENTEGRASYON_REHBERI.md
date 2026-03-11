
# Sare Perfume - Akıllı Koku Danışmanı Shopify Entegrasyon Rehberi

**Hazırlanma Tarihi:** 11 Mart 2026
**Hazırlayan:** Manus AI

---

### Projeye Genel Bakış

Bu rehber, **Sare Perfume** markanız için geliştirilen "Akıllı Koku Danışmanı" sistemini Shopify web sitenize nasıl entegre edeceğinizi adım adım açıklamaktadır. Proje üç ana bileşenden oluşur:

1.  **Zenginleştirilmiş Veri Tabanı:** Orijinal listenizdeki 461 parfüm; koku notaları, mevsim, stil, koku ailesi ve duygusal etiketler gibi 10'dan fazla yeni özellikle zenginleştirilmiştir. Bu veri, `parfum_zenginlestirilmis.xlsx` dosyasında mevcuttur.

2.  **Akıllı Eşleştirme Motoru:** Müşterilerinizin yazdığı duygusal cümleleri veya aradığı özellikleri (`Kumsalda ferah bir akşam` gibi) analiz eden ve bu isteğe en uygun parfümleri bulan yapay zeka modelidir. Bu sistem, açık kaynaklı bir embedding modeli ile GPT-4.1-mini'nin birleşiminden oluşur.

3.  **Shopify Entegrasyonu:** Bu motoru web sitenizde canlı olarak çalışacak bir araca dönüştürme sürecidir. Bu, bir API sunucusu ve sitenizin temasına eklenecek basit bir arayüz kodundan oluşur.

Bu rehber, teknik bilgisi olmayan kullanıcılar için bile takip edilebilir olacak şekilde tasarlanmıştır ve hem **kod ile (en esnek çözüm)** hem de **kodsuz (daha basit) alternatifler** sunar.

---

## Seçenek 1: Kod ile Entegrasyon (Önerilen ve En Güçlü Yöntem)

Bu yöntem, sistemi kendi kontrolünüzdeki bir sunucu üzerinden çalıştırarak size tam esneklik ve ölçeklenebilirlik sunar. Süreç iki ana adıma ayrılmıştır: API sunucusunu internette yayınlamak ve Shopify temanıza bu sunucuyla konuşacak bir arayüz eklemek.

### Adım 1: API Sunucusunu İnternette Yayınlama (Hosting)

Python ile yazdığımız akıllı eşleştirme motorunun internet üzerinden erişilebilir olması gerekir. Bunun için **Render.com** gibi ücretsiz ve kullanımı kolay bir servis kullanacağız.

1.  **Gerekli Dosyaları Hazırlama:**
    *   `app.py`: Web sunucusu kodunuz.
    *   `parfum_embedding_v2.py`: Akıllı eşleştirme motoru kodunuz.
    *   `parfum_zenginlestirilmis.csv`: Zenginleştirilmiş parfüm verileriniz.
    *   `parfum_embeddings_v2.pkl`: Parfüm tanımlarının yapay zeka tarafından işlenmiş vektör hali (en önemli dosya).
    *   `requirements.txt`: Sunucunun ihtiyaç duyduğu tüm Python kütüphaneleri.

2.  **Render.com'a Üye Olma ve Proje Oluşturma:**
    *   [Render.com](https://render.com/) adresine gidin ve ücretsiz bir hesap oluşturun (GitHub hesabınızla bağlanmanız en kolayıdır).
    *   Dashboard'da "**New +**" ve ardından "**Web Service**" butonuna tıklayın.
    *   GitHub hesabınızı bağlayın ve bu proje için yeni bir GitHub deposu (repository) oluşturup tüm dosyaları oraya yükleyin. Ardından bu depoyu Render'da seçin.

3.  **Web Servisini Ayarlama:**
    *   **Name:** Projenize bir isim verin (örn: `sare-perfume-advisor`).
    *   **Region:** Frankfurt (EU Central) seçebilirsiniz.
    *   **Branch:** `main` veya `master` olarak bırakın.
    *   **Runtime:** `Python 3` seçin.
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `gunicorn --workers=1 --threads=4 --bind 0.0.0.0:10000 app:app`
    *   **Instance Type:** `Free` (Ücretsiz) seçeneğini seçin.

4.  **Ortam Değişkeni Ekleme (Çok Önemli):**
    *   "Environment" sekmesine gidin.
    *   "Add Environment Variable" butonuna tıklayın.
    *   **Key:** `OPENAI_API_KEY`
    *   **Value:** Size özel olarak atanan ve `parfum_enrichment.py` scriptinde kullanılan API anahtarınızı buraya yapıştırın. Bu anahtar, kullanıcı sorgularını daha akıllı hale getirmek için gereklidir.

5.  **Yayınlama:**
    *   "Create Web Service" butonuna tıklayın. Render, kodunuzu ve dosyalarınızı alıp sizin için bir sunucu kuracaktır. Bu işlem 5-10 dakika sürebilir.
    *   İşlem bittiğinde, projenizin sayfasında `https://proje-adiniz.onrender.com` şeklinde bir URL göreceksiniz. **Bu sizin API adresinizdir.** Bu adresi bir sonraki adım için saklayın.

### Adım 2: Shopify Temasına Arayüz Ekleme

Şimdi Shopify sitenize, müşterilerinizin koku danışmanını kullanabileceği bir bölüm ekleyeceğiz.

1.  **Shopify Admin Paneline Giriş:**
    *   `Online Store > Themes` bölümüne gidin.
    *   Mevcut temanızda `Customize` butonuna tıklayın.

2.  **Yeni Bir Bölüm (Section) Ekleme:**
    *   Arayüzü eklemek istediğiniz sayfayı seçin (örn: Anasayfa).
    *   Sol menüden "Add section" (Bölüm ekle) seçeneğine tıklayın ve "**Custom Liquid**" adlı bölümü seçin.

3.  **Kodu Yapıştırma:**
    *   Oluşturduğunuz "Custom Liquid" bölümüne tıklayın. Sağda bir kod kutusu açılacaktır.
    *   Aşağıdaki **HTML, CSS ve JavaScript kodunu** bu kutunun içine tamamen yapıştırın.
    *   **ÖNEMLİ:** Kodun içindeki `const API_URL = "https://sare-perfume-advisor.onrender.com/recommend";` satırını, bir önceki adımda Render.com'dan aldığınız kendi API adresinizle güncelleyin.

4.  **Kaydetme:**
    *   Sağ üstteki "Save" butonuna tıklayın. Akıllı Koku Danışmanı artık sayfanızda canlı olmalıdır!

#### Shopify "Custom Liquid" Kodu:

```html
<style>
  #advisor-container {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    max-width: 700px;
    margin: 40px auto;
    padding: 30px;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.07);
    background-color: #ffffff;
  }
  #advisor-title {
    font-size: 26px;
    font-weight: 600;
    color: #1a1a1a;
    text-align: center;
    margin-bottom: 10px;
  }
  #advisor-subtitle {
    font-size: 16px;
    color: #666;
    text-align: center;
    margin-bottom: 30px;
  }
  #advisor-textarea {
    width: 100%;
    padding: 15px;
    font-size: 16px;
    border-radius: 8px;
    border: 1px solid #ccc;
    resize: vertical;
    min-height: 100px;
    box-sizing: border-box;
  }
  #advisor-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 20px;
    gap: 20px;
  }
  #advisor-gender-select {
    padding: 12px;
    font-size: 16px;
    border-radius: 8px;
    border: 1px solid #ccc;
    flex-grow: 1;
  }
  #advisor-submit-btn {
    padding: 12px 30px;
    font-size: 16px;
    font-weight: 500;
    background-color: #000000;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s;
    flex-grow: 2;
  }
  #advisor-submit-btn:hover {
    background-color: #333333;
  }
  #advisor-submit-btn:disabled {
    background-color: #999;
    cursor: not-allowed;
  }
  #advisor-results-container {
    margin-top: 30px;
    border-top: 1px solid #eee;
    padding-top: 20px;
  }
  .advisor-result-item {
    margin-bottom: 25px;
    padding-bottom: 20px;
    border-bottom: 1px solid #f5f5f5;
  }
  .advisor-result-item:last-child {
    border-bottom: none;
  }
  .advisor-result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 18px;
    font-weight: 600;
  }
  .advisor-result-title {
    color: #1a1a1a;
  }
  .advisor-result-score {
    font-size: 14px;
    font-weight: 500;
    padding: 5px 10px;
    border-radius: 15px;
    background-color: #f0fdf4;
    color: #16a34a;
  }
  .advisor-result-details {
    font-size: 14px;
    color: #555;
    margin-top: 8px;
    line-height: 1.6;
  }
  .advisor-result-tags span {
      display: inline-block;
      background-color: #f3f4f6;
      color: #4b5563;
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 12px;
      margin-right: 6px;
      margin-top: 8px;
  }
</style>

<div id="advisor-container">
  <h2 id="advisor-title">Akıllı Koku Danışmanı</h2>
  <p id="advisor-subtitle">Hayalinizdeki anı veya duyguyu anlatın, size en uygun parfümü bulalım.</p>
  
  <textarea id="advisor-textarea" placeholder="Örn: Kumsalda ferah bir akşam... Veya: Ofis için kalıcı ve etkileyici bir koku arıyorum."></textarea>
  
  <div id="advisor-controls">
    <select id="advisor-gender-select">
      <option value="Hepsi">Hepsi</option>
      <option value="Kadın">Kadın</option>
      <option value="Erkek">Erkek</option>
    </select>
    <button id="advisor-submit-btn">Sana Uygun Kokuyu Bul</button>
  </div>
  
  <div id="advisor-results-container"></div>
</div>

<script>
  document.addEventListener('DOMContentLoaded', function() {
    const API_URL = "https://sare-perfume-advisor.onrender.com/recommend"; // <-- BURAYI KENDİ API ADRESİNİZLE DEĞİŞTİRİN

    const queryInput = document.getElementById('advisor-textarea');
    const genderSelect = document.getElementById('advisor-gender-select');
    const submitBtn = document.getElementById('advisor-submit-btn');
    const resultsContainer = document.getElementById('advisor-results-container');

    submitBtn.addEventListener('click', function() {
      const query = queryInput.value.trim();
      const gender = genderSelect.value;

      if (!query) {
        alert('Lütfen bir şeyler yazın.');
        return;
      }

      setLoadingState(true);

      fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: query, gender: gender })
      })
      .then(response => {
          if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
          }
          return response.json();
      })
      .then(data => {
        displayResults(data.recommendations);
        setLoadingState(false);
      })
      .catch(error => {
        console.error('API Hatası:', error);
        resultsContainer.innerHTML = `<p style="color: red; text-align: center;">Bir hata oluştu. Lütfen daha sonra tekrar deneyin.</p>`;
        setLoadingState(false);
      });
    });

    function setLoadingState(isLoading) {
      if (isLoading) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Aranıyor...';
        resultsContainer.innerHTML = '<p style="text-align: center;">Size en uygun kokular bulunuyor, lütfen bekleyin...</p>';
      } else {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sana Uygun Kokuyu Bul';
      }
    }

    function displayResults(recommendations) {
      if (!recommendations || recommendations.length === 0) {
        resultsContainer.innerHTML = '<p style="text-align: center;">Bu tanıma uygun bir koku bulunamadı. Lütfen farklı bir şey deneyin.</p>';
        return;
      }

      let html = '<h3>İşte Size Özel Öneriler:</h3>';
      recommendations.forEach(rec => {
        html += `
          <div class="advisor-result-item">
            <div class="advisor-result-header">
              <span class="advisor-result-title">${rec['Ürün Kodu']} - ${rec['Parfüm Adı']}</span>
              <span class="advisor-result-score">Uyum: ${rec['Benzerlik Skoru']}%</span>
            </div>
            <div class="advisor-result-details">
              ${rec['Açıklama'] || ''}
            </div>
            <div class="advisor-result-tags">
              ${rec['Koku Ailesi'] ? `<span>${rec['Koku Ailesi']}</span>` : ''}
              ${rec['Mevsim'] ? `<span>${rec['Mevsim']}</span>` : ''}
              ${rec['Ortam'] ? `<span>${rec['Ortam']}</span>` : ''}
              ${rec['Cinsiyet'] ? `<span>${rec['Cinsiyet']}</span>` : ''}
            </div>
          </div>
        `;
      });
      resultsContainer.innerHTML = html;
    }
  });
</script>
```

---

## Seçenek 2: Kodsuz Çözüm (Daha Basit, Daha Az Esnek)

Eğer bir sunucuyla uğraşmak istemiyorsanız, bu işi **Make.com** veya **Zapier** gibi bir otomasyon platformu üzerinden, bir **Google Sheets** e-tablosu ve bir **Typeform** formu ile "simüle edebiliriz".

**Bu Yöntemin Mantığı:**

*   **Veri Tabanı:** Zenginleştirilmiş parfüm listeniz bir Google Sheets dosyasında durur.
*   **Arayüz:** Müşteri, Typeform üzerinden bir forma aradığı özellikleri girer.
*   **Zeka:** Make.com/Zapier, form gönderildiğinde tetiklenir, bilgiyi OpenAI'ye (GPT-4) gönderir. GPT-4, bu bilgiyi analiz eder ve Google E-Tablosu'nda hangi satırların en uygun olduğuna karar verir.
*   **Sonuç:** Make.com/Zapier, en uygun parfüm bilgilerini müşteriye e-posta olarak gönderir veya bir web sayfasında gösterir.

**Dezavantajları:**
*   Gerçek zamanlı değildir (sonuç e-posta ile gelir).
*   Embedding kadar "akıllı" değildir, daha çok anahtar kelime eşleştirmeye dayanır.
*   Aylık otomasyon platformu maliyetleri olabilir.

### Adım Adım Kurulum (Make.com ile)

1.  **Google Sheets Hazırlığı:** `parfum_zenginlestirilmis.xlsx` dosyasını Google Drive'a yükleyin ve Google Sheets olarak açın.

2.  **Typeform Hazırlığı:** Typeform'da yeni bir form oluşturun. İçinde "Ne tür bir koku hayal ediyorsunuz?" gibi bir metin alanı ve "Cinsiyet" seçeneği olsun.

3.  **Make.com Senaryosu Oluşturma:**
    *   **Tetikleyici (Trigger):** "Typeform - Watch Responses" modülünü seçin ve formunuza bağlayın.
    *   **Akıl (AI):** "OpenAI - Create a Completion" modülünü ekleyin. Prompt (istek) olarak şunu girin:
        > "Aşağıdaki Google E-tablosunda parfümler bulunmaktadır. Bir müşteri şu isteği gönderdi: `[Typeform'dan gelen metin]`. Bu isteğe en uygun 3 parfümün SADECE 'Kodu' sütunundaki değerlerini virgülle ayırarak yaz. Örneğin: L-101,C-155,T-149"
    *   **Arama:** "Google Sheets - Search Rows" modülünü ekleyin. OpenAI'den gelen kodları kullanarak "Kodu" sütununda arama yapın.
    *   **Sonuç:** "Email - Send an email" modülünü ekleyin. Google Sheets'ten bulunan parfüm bilgilerini formatlayıp müşterinin formda girdiği e-posta adresine gönderin.

Bu yöntem daha fazla manuel ayar gerektirir ancak hiç kod yazmadan ve sunucu yönetmeden bir çözüm sunar.

---

## Sonuç ve Teslim Edilenler

Bu projenin bir parçası olarak aşağıdaki dosyalar hazırlanmış ve tarafınıza teslim edilmek üzere paketlenmiştir:

*   `enson07.10.25.xlsx`: Orijinal parfüm listeniz.
*   `parfum_zenginlestirilmis.xlsx`: Tüm detaylarla zenginleştirilmiş ana veri tabanınız.
*   `demo_test_sonuclari.csv`: Akıllı eşleştirme motorunun test sonuçları.
*   `shopify_api/` (Klasör):
    *   `app.py`: API sunucu kodu.
    *   `parfum_embedding_v2.py`: Eşleştirme motoru kodu.
    *   `requirements.txt`: Sunucu kurulum dosyası.
*   `ENTEGRASYON_REHBERI.md`: Bu rehber.

Umarım bu Akıllı Koku Danışmanı, Sare Perfume markanızın müşteri deneyimini bir üst seviyeye taşır!
