// ─── MIZAN content-script ──────────────────────────────────────────────
// Injects a "⚡ MIZAN" button into each tweet's action bar.
// Saves the tweet text to chrome.storage so the popup can pick it up.
//
// Smart targeting: a tweet that contains ONLY media (images / videos / GIFs)
// with no textual body should NOT receive a MIZAN button — there is nothing
// for the LLM backend to analyze. We still leave un-marked any article whose
// text simply hasn't streamed in yet so the next tick can re-evaluate it.

// ── Text extraction ────────────────────────────────────────────────────
function extractTweetText(article) {
  // Most reliable: the element X marks with data-testid="tweetText"
  const direct = article.querySelector('[data-testid="tweetText"]');
  if (direct && direct.innerText.trim()) return direct.innerText.trim();

  // Fallbacks for older / edge-case markup
  const lang = article.querySelector('div[lang]');
  if (lang && lang.innerText.trim()) return lang.innerText.trim();

  return "";
}

// ── Media detection ────────────────────────────────────────────────────
// True when the tweet has any visible image / video / GIF / external card image.
function tweetHasMedia(article) {
  return !!(
    article.querySelector('[data-testid="tweetPhoto"]')      ||
    article.querySelector('[data-testid="videoPlayer"]')     ||
    article.querySelector('[data-testid="videoComponent"]')  ||
    article.querySelector('div[aria-label="Embedded video"]')||
    article.querySelector('a[href*="/photo/"]')              ||
    article.querySelector('img[alt="Image"]')
  );
}

// True only when the tweet has media AND no extractable text body.
function isMediaOnlyTweet(article) {
  if (extractTweetText(article)) return false;   // has text → not media-only
  return tweetHasMedia(article);
}

// ── Button injection ───────────────────────────────────────────────────
function addDigitaButton() {
  // Only target action bars that sit INSIDE an <article> (i.e. real tweets,
  // not modals, sidebars, or unrelated role="group" containers).
  const articles = document.querySelectorAll(
    'article:not([data-MIZAN-added]):not([data-MIZAN-skip])'
  );

  articles.forEach((article) => {
    // Skip media-only tweets permanently — there is no text for MIZAN.
    if (isMediaOnlyTweet(article)) {
      article.setAttribute('data-MIZAN-skip', 'media-only');
      return;
    }

    // No text yet AND no media → tweet body probably hasn't rendered.
    // Leave the article un-marked so the next interval tick re-checks it.
    const tweetText = extractTweetText(article);
    if (!tweetText) return;

    const bar = article.querySelector('div[role="group"]');
    if (!bar) return;
    if (bar.querySelector('.MIZAN-btn')) {
      article.setAttribute('data-MIZAN-added', 'true');
      return;
    }

    const btn = document.createElement('button');
    btn.className = 'MIZAN-btn';
    btn.type = 'button';
    btn.innerHTML = '⚡ MIZAN';
    btn.title = 'تحليل هذه التغريدة باستخدام MIZAN AI';
    btn.style.cssText = `
      background: rgba(0, 242, 255, 0.10);
      border: 1px solid rgba(0, 242, 255, 0.35);
      color: #00f2ff;
      padding: 2px 12px;
      border-radius: 99px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      margin-right: 12px;
      margin-left: auto;
      transition: all 0.2s ease;
      font-family: inherit;
    `;

    btn.onmouseenter = () => { btn.style.background = 'rgba(0, 242, 255, 0.22)'; };
    btn.onmouseleave = () => { btn.style.background = 'rgba(0, 242, 255, 0.10)'; };

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      // Re-extract at click-time in case the tweet was edited / expanded.
      const text = extractTweetText(article);
      if (!text) {
        flash(btn, '⚠️ لا يوجد نص', '#ffb700');
        return;
      }
      if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
        flash(btn, '⚠️ لا يمكن الحفظ', '#ff3c5f');
        return;
      }
      chrome.storage.local.set({ pendingText: text }, () => {
        flash(btn, '✅ جاهز — افتح MIZAN', '#00ffb2');
      });
    });

    bar.appendChild(btn);
    article.setAttribute('data-MIZAN-added', 'true');
  });
}

function flash(btn, msg, color) {
  const old      = btn.innerHTML;
  const oldBg    = btn.style.background;
  btn.innerHTML = msg;
  btn.style.borderColor = color;
  btn.style.color       = color;
  setTimeout(() => {
    btn.innerHTML         = old;
    btn.style.background  = oldBg;
    btn.style.borderColor = 'rgba(0, 242, 255, 0.35)';
    btn.style.color       = '#00f2ff';
  }, 1800);
}

// Run on a steady cadence — X re-renders tweets on scroll
setInterval(addDigitaButton, 1500);
addDigitaButton();
