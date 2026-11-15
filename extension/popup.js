// ─── MIZAN popup ─────────────────────────────────────────────────────────
const API_BASE   = "http://127.0.0.1:5000";
const API_URL    = `${API_BASE}/predict`;
const HEALTH_URL = `${API_BASE}/health`;
const SITE_URL   = `${API_BASE}/`;     // MIZAN website (served by the same Flask app)

// Server-side analysis can take up to ~20 s. Hard-cap the request a little
// above that so the popup never spins forever.
const REQUEST_TIMEOUT_MS = 90_000;
// We don't get real progress events from the backend, so we drive the bar
// against a soft ETA. It eases out before 100% so it doesn't *look* stuck.
const PROGRESS_ETA_MS    = 60_000;

const txtEl       = document.getElementById("txt");
const goBtn       = document.getElementById("go");
const openBtn     = document.getElementById("openWeb");
const reload      = document.getElementById("reload");
const resDiv      = document.getElementById("res");
const dot         = document.getElementById("serverDot");
const loadingBox  = document.getElementById("loading");
const loadingMsg  = document.getElementById("loadingMsg");
const progressFill= document.getElementById("progressFill");
const progressPct = document.getElementById("progressPct");
const progressEta = document.getElementById("progressEta");
const themeToggle = document.getElementById("themeToggle");

// ─── Theme toggle ─────────────────────────────────────────────────────────
// Persisted: chrome.storage → "digitaTheme" ∈ {"auto","dark","light"}
function applyTheme(mode) {
  if (mode === "dark" || mode === "light") {
    document.documentElement.setAttribute("data-theme", mode);
  } else {
    document.documentElement.setAttribute("data-theme", "auto");
    document.documentElement.removeAttribute("data-theme"); // fall back to @media
  }
}
chrome.storage?.local?.get?.(["digitaTheme"], (data) => {
  applyTheme((data && data.digitaTheme) || "auto");
});
themeToggle?.addEventListener("click", () => {
  const cur  = document.documentElement.getAttribute("data-theme") || "auto";
  const next = cur === "dark" ? "light" : cur === "light" ? "auto" : "dark";
  applyTheme(next);
  chrome.storage?.local?.set?.({ digitaTheme: next });
});

// ─── Restore the tweet text the content-script saved ───────────────────────
chrome.storage.local.get(["pendingText"], (data) => {
  if (data && data.pendingText) {
    txtEl.value = data.pendingText;
    // keep it around for the "Open in MIZAN" handoff
  }
});

// ─── Server health indicator ──────────────────────────────────────────────
async function pingServer() {
  try {
    const r = await fetch(HEALTH_URL, { method: "GET", cache: "no-store" });
    if (r.ok) { dot.classList.add("online");  dot.classList.remove("offline"); return true; }
  } catch (_) {}
  dot.classList.add("offline"); dot.classList.remove("online");
  return false;
}
pingServer();

// ─── "Open in MIZAN" — hand off the tweet to the full website ────────────
openBtn.addEventListener("click", () => {
  const text = (txtEl.value || "").trim();
  chrome.storage.local.set({ "digitaHandoff": { text, ts: Date.now() } });
  const url = text
    ? `${SITE_URL}?MIZAN_text=${encodeURIComponent(text)}&MIZAN_auto=1`
    : SITE_URL;
  chrome.tabs.create({ url });
});

reload.addEventListener("click", (e) => {
  e.preventDefault();
  resDiv.style.display = "none";
  resDiv.innerHTML = "";
  hideLoading();
  pingServer();
});

// ─── Progress bar driver ──────────────────────────────────────────────────
let progressTimer = null;
let progressStart = 0;

function showLoading(message) {
  loadingMsg.textContent = message || "جاري التحليل...";
  loadingBox.style.display = "block";
  resDiv.style.display = "none";
  resDiv.innerHTML = "";

  progressStart = performance.now();
  progressFill.style.width = "0%";
  progressPct.textContent  = "0%";

  if (progressTimer) clearInterval(progressTimer);
  progressTimer = setInterval(() => {
    const elapsed = performance.now() - progressStart;
    // Ease-out: approach but don't reach 95% over PROGRESS_ETA_MS.
    const t   = Math.min(1, elapsed / PROGRESS_ETA_MS);
    const pct = Math.min(95, Math.round(95 * (1 - Math.pow(1 - t, 2))));
    progressFill.style.width = pct + "%";
    progressPct.textContent  = pct + "%";

    const remaining = Math.max(0, Math.ceil((PROGRESS_ETA_MS - elapsed) / 1000));
    progressEta.textContent = remaining > 0 ? `~${remaining} ثانية` : "اللحظة الأخيرة...";

    if (elapsed > PROGRESS_ETA_MS + 5000) {
      loadingMsg.textContent = "الخادم يستغرق وقتاً أطول من المعتاد...";
    }
  }, 200);
}

function finishLoading() {
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
  progressFill.style.width = "100%";
  progressPct.textContent  = "100%";
  progressEta.textContent  = "تم";
  // Brief flash of "100%" before the verdict slides in.
  setTimeout(hideLoading, 250);
}

function hideLoading() {
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
  loadingBox.style.display = "none";
}

// ─── Analyze button ───────────────────────────────────────────────────────
goBtn.addEventListener("click", async () => {
  const text = txtEl.value.trim();

  if (!text) {
    showInfo("⚠️ أدخل نصاً أولاً، أو اسحب تغريدة من X باستخدام زر ⚡ MIZAN.");
    return;
  }

  goBtn.disabled = true;
  goBtn.textContent = "جاري التحليل...";
  showLoading("جاري الإرسال للسيرفر... قد يستغرق حتى دقيقة.");

  // AbortController + setTimeout = a real client-side request timeout.
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(API_URL, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ text }),
      signal:  ctrl.signal,
    });
    clearTimeout(timer);

    if (!response.ok) {
      let err = `HTTP ${response.status}`;
      try { const j = await response.json(); err = j.error || err; } catch (_) {}
      throw new Error(err);
    }

    const result = await response.json();
    finishLoading();
    renderResult(result, text);
    pingServer();   // refresh dot to "online" on success

  } catch (error) {
    clearTimeout(timer);
    hideLoading();
    console.error("[MIZAN] analyze failed:", error);

    if (error.name === "AbortError") {
      showError("⌛ انتهت مهلة الطلب (90 ثانية). جرّب نصاً أقصر أو تأكّد من حالة السيرفر.");
      return;
    }

    const looksOffline =
      /failed to fetch|networkerror|load failed/i.test(String(error.message)) ||
      error.name === "TypeError";

    if (looksOffline) {
      dot.classList.add("offline"); dot.classList.remove("online");
      showError(
        "❌ السيرفر غير متصل.<br>" +
        "شغّل السيرفر أولاً:<br><code>python backend.py</code><br>" +
        "ثم اضغط <b>↻ إعادة الفحص</b>."
      );
    } else {
      showError(`❌ خطأ: ${escapeHtml(error.message)}`);
    }
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = "تحليل المصداقية";
  }
});

// ─── Render the rich result card ──────────────────────────────────────────
function renderResult(result, originalText) {
  // Backend returns: status, final_score, ai_real, ai_fake, similarity,
  // repetition_count, found_in_sources, top4_sources, best_url, summary.
  const status      = result.status       || "";
  const finalScore  = clampPct(result.final_score);
  const aiReal      = clampPct(result.ai_real);
  const aiFake      = clampPct(result.ai_fake);
  const similarity  = clampPct(result.similarity);
  const reps        = result.repetition_count || 0;
  const sources     = (result.top4_sources || result.found_in_sources || []).slice(0, 4);
  const bestUrl     = result.best_url || "";

  // Tier comes from the LLM-driven status / score — no client-side keyword
  // heuristics. (The previous "Urgent / فضيحة" keyword fallback has been
  // removed; we lean entirely on the backend for contextual analysis.)
  let tier, label;
  if (/Real|Verified|موثوق/i.test(status) || finalScore >= 70) {
    tier = "real"; label = "✅ محتوى موثوق";
  } else if (/Suspicious|مشبوه/i.test(status) || finalScore >= 40) {
    tier = "suspicious"; label = "⚠️ محتوى مشبوه";
  } else {
    tier = "fake"; label = "❌ محتوى مضلّل";
  }

  // Each source pill is a clickable link. If the backend gave us a URL,
  // we open it directly; otherwise we open a Google search restricted to
  // that source name + the analyzed text so users can verify quickly.
  const sourcesHtml = sources.length
    ? `<div class="sources">${sources.map(s => {
        const raw = String(s ?? "");
        const isUrl = /^https?:\/\//i.test(raw);
        const href  = isUrl
          ? raw
          : `https://www.google.com/search?q=${encodeURIComponent(`"${raw}" ${originalText.slice(0, 80)}`)}`;
        const label = isUrl ? hostnameOf(raw) : raw;
        return `<a class="src-pill" href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer" title="${escapeAttr(raw)}">${escapeHtml(label)}</a>`;
      }).join("")}</div>`
    : "";

  const bestUrlHtml = bestUrl
    ? `<div class="meta" style="margin-top:6px;"><a href="${escapeAttr(bestUrl)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent-2);text-decoration:none;">🔗 المصدر الأكثر تطابقاً (${escapeHtml(hostnameOf(bestUrl))})</a></div>`
    : "";

  resDiv.style.display = "block";
  resDiv.innerHTML = `
    <div class="verdict-card ${tier}">
      <div class="verdict-label">${label}</div>

      <div class="score-row"><span>الثقة الإجمالية</span><b>${finalScore}%</b></div>
      <div class="bar"><div class="bar-fill" style="width:${finalScore}%"></div></div>

      <div class="meta">
        <div>🧠 <b>الذكاء الاصطناعي:</b> حقيقي ${aiReal}% &nbsp;|&nbsp; مضلّل ${aiFake}%</div>
        <div>🔍 <b>التشابه مع المصادر:</b> ${similarity}%</div>
        <div>📰 <b>عدد المصادر المؤكِّدة:</b> ${reps}</div>
      </div>
      ${sourcesHtml}
      ${bestUrlHtml}

      <div class="verdict-actions">
        <button id="copyVerdict" type="button" title="نسخ نتيجة MIZAN">📋 نسخ النتيجة</button>
        <a id="shareX" href="#" title="نشر النتيجة على X">𝕏 مشاركة على X</a>
      </div>
    </div>
    <div class="footer" style="margin-top:10px;">
      <a id="openFull">عرض التحليل الكامل في موقع MIZAN →</a>
    </div>
  `;

  // ── Wire dynamic buttons ──────────────────────────────────────────────
  const openFull = document.getElementById("openFull");
  if (openFull) {
    openFull.addEventListener("click", (e) => { e.preventDefault(); openBtn.click(); });
  }

  const verdictText = buildVerdictText({
    label, finalScore, aiReal, aiFake, similarity, reps, bestUrl, originalText
  });

  const copyBtn = document.getElementById("copyVerdict");
  copyBtn?.addEventListener("click", async () => {
    const ok = await copyToClipboard(verdictText);
    const original = copyBtn.textContent;
    copyBtn.textContent = ok ? "✅ تم النسخ" : "⚠️ تعذّر النسخ";
    copyBtn.classList.toggle("copied", ok);
    setTimeout(() => {
      copyBtn.textContent = original;
      copyBtn.classList.remove("copied");
    }, 1600);
  });

  const shareX = document.getElementById("shareX");
  if (shareX) {
    // X / Twitter web intent — opens a pre-filled tweet composer.
    const intent = `https://twitter.com/intent/tweet?text=${encodeURIComponent(verdictText)}`;
    shareX.setAttribute("href", intent);
    shareX.setAttribute("target", "_blank");
    shareX.setAttribute("rel", "noopener noreferrer");
  }
}

// ─── helpers ──────────────────────────────────────────────────────────────
function buildVerdictText({ label, finalScore, aiReal, aiFake, similarity, reps, bestUrl, originalText }) {
  const lines = [
    `${label} — MIZAN AI`,
    `الثقة الإجمالية: ${finalScore}%`,
    `الذكاء الاصطناعي: حقيقي ${aiReal}% | مضلّل ${aiFake}%`,
    `التشابه مع المصادر: ${similarity}%`,
    `المصادر المؤكِّدة: ${reps}`,
  ];
  if (bestUrl) lines.push(`المصدر الأكثر تطابقاً: ${bestUrl}`);
  if (originalText) {
    const snippet = originalText.length > 120
      ? originalText.slice(0, 117) + "..."
      : originalText;
    lines.push("", `النص: "${snippet}"`);
  }
  return lines.join("\n");
}

async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) { /* fall through to legacy path */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity  = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) { return false; }
}

function hostnameOf(u) {
  try { return new URL(u).hostname.replace(/^www\./, ""); }
  catch (_) { return u; }
}

function showInfo(html) {
  hideLoading();
  resDiv.style.display = "block";
  resDiv.innerHTML = `<div class="info-msg">${html}</div>`;
}
function showError(html) {
  hideLoading();
  resDiv.style.display = "block";
  resDiv.innerHTML = `<div class="err-msg">${html}</div>`;
}
function clampPct(v) {
  const n = Number(v);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n * 100) / 100));
}
function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }
