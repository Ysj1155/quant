window.loadWatchlist = function () {
  window.loadJsonAndRender("/get_watchlist", (data) => {
    const ul = window.$("watchlist-items");
    if (!ul) return;

    ul.innerHTML = "";
    (data.watchlist || []).forEach((t) => ul.appendChild(window.createWatchlistItem(t)));
  });
};

window.setupWatchlistForm = function () {
  const form = window.$("watchlist-form");
  if (!form || window.AppBound.watchlistForm) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = window.$("ticker");
    const ticker = (input?.value || "").trim().toUpperCase();
    if (!ticker) return;

    fetch("/add_watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.error) return alert(res.error);
        window.$("watchlist-items")?.appendChild(window.createWatchlistItem(ticker));
        if (input) input.value = "";
      });
  });

  window.AppBound.watchlistForm = true;
};

window.createWatchlistItem = function (ticker) {
  const li = document.createElement("li");
  li.className = "list-group-item";
  li.style.display = "flex";
  li.style.justifyContent = "space-between";
  li.style.alignItems = "center";

  const span = document.createElement("span");
  span.textContent = ticker;
  span.style.cursor = "pointer";
  span.title = "클릭하면 분석 정보를 확인합니다";
  span.addEventListener("click", () => window.openStockDetail(ticker));

  const del = document.createElement("button");
  del.textContent = "❌";
  del.style.border = "none";
  del.style.background = "none";
  del.style.cursor = "pointer";
  del.style.color = "red";
  del.title = "관심 목록에서 제거";
  del.addEventListener("click", () => {
    if (!confirm(`${ticker} 티커를 관심 목록에서 삭제할까요?`)) return;
    fetch("/remove_watchlist", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.error) return alert(res.error);
        li.remove();
      });
  });

  li.appendChild(span);
  li.appendChild(del);
  return li;
};

window.openStockDetail = function (ticker) {
  const panel = window.$("stock-detail-panel");
  const content = window.$("detail-content");
  if (!panel || !content) return;

  content.innerHTML = `<p>🔄 데이터 로딩중...</p>`;

  fetch(`/get_stock_detail_finnhub?ticker=${encodeURIComponent(ticker)}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        content.innerHTML = `<p style="color:red;">❌ ${data.error}</p>`;
        return;
      }

      window.renderFinnhubBasic(content, ticker, data);
      window.renderValuationBox(content, ticker, data);
      window.renderKisCandleChart(content, ticker);
    })
    .catch((err) => {
      console.error("Finnhub fetch error:", err);
      content.innerHTML = `<p style="color:red;">❌ Finnhub 데이터 요청 실패</p>`;
    });

  panel.style.display = "block";
};

window.renderFinnhubBasic = function (root, ticker, data) {
  const price = data.price?.c ?? "N/A";
  const marketCap = data.profile?.marketCapitalization ?? "N/A";
  const per = data.metrics?.metric?.peTTM ?? "N/A";
  const dividendYield = (data.metrics?.metric?.currentDividendYieldTTM ?? 0) * 100;

  root.innerHTML = `
    <h5>${data.profile?.name ?? ""} (${ticker})</h5>
    <p><strong>📈 현재가:</strong> $${price}</p>
    <p><strong>💰 시가총액:</strong> ${window.formatMarketCap(marketCap)}</p>
    <p><strong>📊 PER:</strong> ${per}</p>
    <p><strong>📤 배당률:</strong> ${Number(dividendYield).toFixed(2)}%</p>
  `;
};

window.renderValuationBox = function (root, ticker, finnhubData) {
  const valBox = document.createElement("div");
  valBox.style.marginTop = "12px";
  valBox.innerHTML = `<p>🔄 적정주가/목표가 계산중...</p>`;
  root.appendChild(valBox);

  const cur = finnhubData.price?.c ?? null;
  const curNum = cur == null || cur === "N/A" ? null : Number(cur);

  fetch(`/api/valuation?ticker=${encodeURIComponent(ticker)}`)
    .then((r) => r.json())
    .then((v) => {
      if (v.error) {
        valBox.innerHTML = `<p style="color:red;">❌ valuation error: ${v.error}</p>`;
        return;
      }

      const myOk = v.my_model?.ok;
      const myFair = myOk ? Number(v.my_model.fair_price) : null;

      const tMean = v.finnhub_target?.targetMean != null ? Number(v.finnhub_target.targetMean) : null;
      const tHigh = v.finnhub_target?.targetHigh != null ? Number(v.finnhub_target.targetHigh) : null;
      const tLow = v.finnhub_target?.targetLow != null ? Number(v.finnhub_target.targetLow) : null;

      function upsidePct(target) {
        if (curNum == null || !isFinite(curNum) || target == null || !isFinite(target) || curNum === 0) return null;
        return ((target - curNum) / curNum) * 100.0;
      }

      const upMy = upsidePct(myFair);
      const upMean = upsidePct(tMean);

      const fmt = (x) => (x == null || !isFinite(x) ? "N/A" : x.toLocaleString(undefined, { maximumFractionDigits: 2 }));
      const fmtPct = (x) => (x == null || !isFinite(x) ? "N/A" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`);

      valBox.innerHTML = `
        <hr>
        <h5>🧠 적정주가/목표가 비교</h5>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <div class="mini-card">
            <div class="mini-card-title">내 모델 적정주가 (EV/발행주식수)</div>
            <div class="mini-card-value">$${fmt(myFair)}</div>
            <div class="mini-card-sub">현재가 대비: ${fmtPct(upMy)}</div>
          </div>
          <div class="mini-card">
            <div class="mini-card-title">Finnhub 목표가(평균)</div>
            <div class="mini-card-value">$${fmt(tMean)}</div>
            <div class="mini-card-sub">현재가 대비: ${fmtPct(upMean)}</div>
          </div>
        </div>
        <div style="margin-top:8px; font-size:12px; opacity:0.8;">
          Finnhub 범위: low $${fmt(tLow)} / high $${fmt(tHigh)}
        </div>
      `;
    })
    .catch((err) => {
      console.error("valuation fetch error:", err);
      valBox.innerHTML = `<p style="color:red;">❌ valuation fetch failed</p>`;
    });
};

window.renderKisCandleChart = function (root, ticker) {
  const chartDiv = document.createElement("div");
  chartDiv.id = "kis-candle-chart";
  chartDiv.style.height = "500px";
  chartDiv.style.marginTop = "20px";
  chartDiv.innerHTML = `<span id="kis-loading-text">🔄 KIS 캔들차트 로딩중...</span>`;
  root.appendChild(chartDiv);

  fetch(`/get_stock_chart_kis?ticker=${encodeURIComponent(ticker)}&exchange=NAS`)
    .then((r) => r.json())
    .then((kis) => {
      if (kis.error) {
        chartDiv.innerHTML = `<p style="color:red;">KIS 데이터 불러오기 실패: ${kis.error}</p>`;
        return;
      }

      const ohlc = kis.ohlc || [];
      const dates = ohlc.map((x) => `${x.date.slice(0, 4)}-${x.date.slice(4, 6)}-${x.date.slice(6, 8)}`);
      const opens = ohlc.map((x) => x.open);
      const highs = ohlc.map((x) => x.high);
      const lows = ohlc.map((x) => x.low);
      const closes = ohlc.map((x) => x.close);
      const vols = ohlc.map((x) => x.volume);

      Plotly.newPlot(
        "kis-candle-chart",
        [
          { x: dates, open: opens, high: highs, low: lows, close: closes, type: "candlestick", name: "Price", xaxis: "x", yaxis: "y" },
          { x: dates, y: vols, type: "bar", name: "Volume", xaxis: "x", yaxis: "y2", marker: { color: "rgba(128,128,128,0.4)" } },
        ],
        {
          title: `${ticker} 캔들차트 (KIS API)`,
          xaxis: { title: "날짜", rangeslider: { visible: false } },
          yaxis: { title: "가격", domain: [0.3, 1] },
          yaxis2: { title: "거래량", domain: [0, 0.2], showticklabels: true },
          height: 500,
          margin: { t: 40, b: 50 },
          showlegend: false,
        },
        { responsive: true }
      ).then(() => {
        window.$("kis-loading-text")?.remove();
      });
    })
    .catch((err) => {
      console.error("KIS fetch error:", err);
      chartDiv.innerHTML = `<p style="color:red;">KIS 캔들차트 로드 실패</p>`;
    });
};