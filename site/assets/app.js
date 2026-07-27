const state = {
  books: [],
  sort: "likes",
  query: "",
  chartLimit: { likes: 8, views: 8, comments: 8 },
  chartRanked: { likes: [], views: [], comments: [] },
  chartsObserved: false,
};

const BATCH = 8;
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

function fmt(n) {
  return new Intl.NumberFormat("ru-RU").format(n || 0);
}

function fmtCompact(n) {
  const v = n || 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v >= 10_000_000 ? 0 : 1).replace(".0", "")} млн`;
  if (v >= 10_000) return `${Math.round(v / 1000)} тыс`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(".0", "")} тыс`;
  return fmt(v);
}

function sortBooks(list) {
  const copy = [...list];
  if (state.sort === "comments") {
    copy.sort((a, b) => (b.comments || 0) - (a.comments || 0) || (b.likes || 0) - (a.likes || 0));
  } else if (state.sort === "number") {
    copy.sort((a, b) => (b.number || 0) - (a.number || 0));
  } else if (state.sort === "views") {
    copy.sort((a, b) => (b.views || 0) - (a.views || 0));
  } else {
    copy.sort((a, b) => (b.likes || 0) - (a.likes || 0) || (b.comments || 0) - (a.comments || 0));
  }
  return copy;
}

function filtered() {
  const q = state.query.trim().toLowerCase();
  let list = state.books;
  if (q) {
    list = list.filter((b) => {
      const hay = `${b.title} ${b.author} ${b.takeaway} ${b.number} ${b.hashtag || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }
  return sortBooks(list);
}

function rankedBy(metric) {
  return [...state.books]
    .filter((b) => (b[metric] || 0) > 0)
    .sort((a, b) => (b[metric] || 0) - (a[metric] || 0));
}

function renderChart(containerId, metric, { animate = false } = {}) {
  const el = $(containerId);
  if (!el) return;

  const all = state.chartRanked[metric];
  const limit = state.chartLimit[metric];
  const rows = all.slice(0, limit);
  const max = all[0]?.[metric] || 1;
  const remaining = Math.max(0, all.length - limit);

  el.innerHTML = rows
    .map((b, i) => {
      const value = b[metric] || 0;
      const pct = Math.max(4, Math.round((value / max) * 100));
      const short = (b.title || "").length > 42 ? `${b.title.slice(0, 40)}…` : b.title;
      const delay = ((i % BATCH) * 0.05).toFixed(2);
      return `
        <div class="bar-row" title="${escapeHtml(b.title)} · ${fmt(value)}">
          <div class="bar-row__label">
            <span class="bar-row__rank">#${i + 1}</span>
            <span class="bar-row__title">${escapeHtml(short)}</span>
          </div>
          <div class="bar-row__track" aria-hidden="true">
            <div class="bar-row__fill" style="--w:${pct}%; transition-delay:${delay}s"></div>
          </div>
          <div class="bar-row__value">${metric === "views" ? fmtCompact(value) : fmt(value)}</div>
        </div>`;
    })
    .join("");

  const btn = $(`.chart-more[data-metric="${metric}"]`);
  if (btn) {
    if (remaining > 0) {
      const next = Math.min(BATCH, remaining);
      btn.hidden = false;
      btn.textContent = remaining > BATCH ? `Ещё ${BATCH}` : `Ещё ${next}`;
      btn.setAttribute("aria-label", `Показать ещё ${next} книг по ${metric}`);
    } else {
      btn.hidden = true;
    }
  }

  if (animate) {
    const section = $("#charts");
    if (!section) return;
    section.classList.remove("is-visible");
    requestAnimationFrame(() => {
      requestAnimationFrame(() => section.classList.add("is-visible"));
    });
  }
}

function renderCharts({ animate = false } = {}) {
  state.chartRanked = {
    likes: rankedBy("likes"),
    views: rankedBy("views"),
    comments: rankedBy("comments"),
  };
  renderChart("#chart-likes", "likes", { animate });
  renderChart("#chart-views", "views", { animate });
  renderChart("#chart-comments", "comments", { animate });
  if (!state.chartsObserved) observeCharts();
}

function expandChart(metric) {
  const all = state.chartRanked[metric] || rankedBy(metric);
  if (state.chartLimit[metric] >= all.length) return;
  state.chartLimit[metric] = Math.min(all.length, state.chartLimit[metric] + BATCH);
  renderChart(`#chart-${metric}`, metric, { animate: true });
}

function observeCharts() {
  const section = $("#charts");
  if (!section || state.chartsObserved) return;
  state.chartsObserved = true;

  const reveal = () => section.classList.add("is-visible");

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    reveal();
    return;
  }

  if (!("IntersectionObserver" in window)) {
    reveal();
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        reveal();
        io.disconnect();
      }
    },
    { threshold: 0.2 }
  );
  io.observe(section);
}

function render() {
  const list = filtered();
  const grid = $("#grid");
  $("#count").textContent = fmt(state.books.length);
  $("#shown").textContent = fmt(list.length);
  const topLikes = Math.max(0, ...state.books.map((b) => b.likes || 0));
  $("#topLikes").textContent = fmt(topLikes);

  if (!list.length) {
    grid.innerHTML = `<div class="empty">Ничего не найдено. Попробуйте другой запрос.</div>`;
    return;
  }

  grid.innerHTML = list
    .map((b, i) => {
      const cover = b.cover || b.cover_remote || "covers/_placeholder.svg";
      const delay = Math.min(i, 12) * 0.03;
      return `
      <article class="card" style="animation-delay:${delay}s">
        <div class="cover-wrap">
          <span class="rank">TOP ${i + 1}</span>
          <img src="${cover}" alt="Обложка: ${escapeHtml(b.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='covers/_placeholder.svg'">
          <div class="meta-badges">
            <span class="badge likes">Лайки ${fmt(b.likes)}</span>
            <span class="badge comments">Комменты ${fmt(b.comments)}</span>
          </div>
        </div>
        <div class="body">
          <div class="num">Книга #${b.number}</div>
          <h2>${escapeHtml(b.title)}</h2>
          <p class="author">${escapeHtml(b.author || "Автор не указан")}</p>
          <p class="takeaway">${escapeHtml(b.takeaway || "")}</p>
          <div class="foot">
            <span>${b.date ? escapeHtml(b.date) : "—"}</span>
            <span>${fmt(b.views)} просм.</span>
          </div>
        </div>
      </article>`;
    })
    .join("");
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function boot() {
  const res = await fetch("./data/books.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Не удалось загрузить books.json");
  const payload = await res.json();
  state.books = payload.books || [];

  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    render();
  });
  $("#sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    render();
  });
  $$(".chart-more").forEach((btn) => {
    btn.addEventListener("click", () => expandChart(btn.dataset.metric));
  });

  renderCharts();
  render();
}

boot().catch((err) => {
  $("#grid").innerHTML = `<div class="empty">Ошибка загрузки каталога: ${escapeHtml(err.message)}</div>`;
});
