window.AppState = {
  dataTabLoaded: false,
  intervals: {
    marketCards: null,
  },
};

window.AppBound = {
  profitChartClick: false,
  watchlistForm: false,
  privacyToggle: false,
};

window.$ = function (id) {
  return document.getElementById(id);
};

window.safeText = function (el, text) {
  if (!el) return;
  el.textContent = text;
};

window.safeHTML = function (el, html) {
  if (!el) return;
  el.innerHTML = html;
};

window.normalizeDate = function (x) {
  return String(x).slice(0, 10);
};

window.formatMarketCap = function (value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "N/A";
  const v = Number(value);
  const billion = 1_000_000_000;
  const million = 1_000_000;
  if (v >= billion) return (v / billion).toFixed(1) + "B";
  if (v >= million) return (v / million).toFixed(1) + "M";
  return v.toLocaleString();
};

window.toLocaleNum = function (x, digits = 0) {
  const n = Number(x);
  if (!isFinite(n)) return "N/A";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
};

window.escapeHTML = function (value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

window.loadJsonAndRender = function (url, onSuccess, onError) {
  window
    .fetchJsonCached(url, 15000)
    .then((data) => {
      if (data?.error) {
        console.error(`❌ Error from ${url}:`, data.error);
        onError && onError(data.error);
      } else {
        onSuccess(data);
      }
    })
    .catch((err) => {
      console.error(`❌ Fetch failed from ${url}:`, err);
      onError && onError(err);
    });
};

window.forceRelayout = function (id) {
  const el = window.$(id);
  if (!el) return;

  const parent = el.closest(".chart-card") || el.parentElement || el;
  const cs = getComputedStyle(parent);
  const padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
  const contentW = Math.max(320, Math.floor(parent.clientWidth - padX));

  const isSquare = el.classList.contains("square-plot");
  const aspectAttr = el.dataset.aspect ? parseFloat(el.dataset.aspect) : null;
  const aspect = isSquare ? 1 : (aspectAttr || 0.56);

  const h = Math.max(240, Math.round(contentW * aspect));

  const mTop = parseInt(el.dataset.marginT || 10, 10);
  const mRight = parseInt(el.dataset.marginR || 10, 10);
  const mLeft = parseInt(el.dataset.marginL || 40, 10);
  const mBottom = parseInt(el.dataset.marginB || 60, 10);

  try {
    Plotly.relayout(el, {
      width: contentW,
      height: h,
      margin: { t: mTop, r: mRight, l: mLeft, b: mBottom },
      xaxis: { automargin: true },
      yaxis: { automargin: true },
    });
  } catch (e) {
    // plot 생성 전일 수 있음
  }
};

window.safePlotlyResize = function (id) {
  const el = window.$(id);
  if (!el) return;
  try {
    Plotly.Plots.resize(el);
  } catch (e) {}
};

const _clientCache = new Map();
const _inflight = new Map();

window.fetchJsonCached = function (url, ttlMs = 15000) {
  const now = Date.now();
  const hit = _clientCache.get(url);
  if (hit && hit.exp > now) return Promise.resolve(hit.data);

  const inflight = _inflight.get(url);
  if (inflight) return inflight;

  const p = fetch(url)
    .then((r) => r.json())
    .then((data) => {
      _clientCache.set(url, { exp: now + ttlMs, data });
      return data;
    })
    .finally(() => _inflight.delete(url));

  _inflight.set(url, p);
  return p;
};
