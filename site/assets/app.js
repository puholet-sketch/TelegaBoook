const state = {
  books: [],
  sort: "likes",
  query: "",
};

const $ = (sel) => document.querySelector(sel);

function fmt(n) {
  return new Intl.NumberFormat("ru-RU").format(n || 0);
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
  render();
}

boot().catch((err) => {
  $("#grid").innerHTML = `<div class="empty">Ошибка загрузки каталога: ${escapeHtml(err.message)}</div>`;
});
