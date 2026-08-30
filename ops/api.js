// Общий слой для всех страниц внутреннего модуля (login/report/map/admin):
// адрес бэкенда, обёртка над fetch с JWT, проверка роли при входе на страницу,
// общая шапка навигации.

// Адрес бэкенда FastAPI. При разворачивании на боевом стенде поменяйте на
// реальный адрес API (например, "https://ops-api.example.org").
//
// Автоопределение для GitHub Codespaces: там фронтенд и бэкенд открыты на
// двух разных проброшенных портах одного codespace — каждый со своим
// поддоменом вида "<codespace>-<порт>.app.github.dev". Подставляем порт
// бэкенда (8000) в тот же поддомен, чтобы не редактировать это вручную
// при каждом новом codespace.
const API_BASE = (() => {
  const host = window.location.host;
  const match = host.match(/^(.*)-(\d+)(\.app\.github\.dev)$/);
  if (match) {
    return `${window.location.protocol}//${match[1]}-8000${match[3]}`;
  }
  return "http://localhost:8000";
})();

const TOKEN_KEY = "tmap_token";
const USER_KEY = "tmap_user";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function logout() {
  clearSession();
  window.location.href = "login.html";
}

// options.form = true — отправить options.body (объект) как
// application/x-www-form-urlencoded (нужно для /auth/login).
async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = Object.assign({}, options.headers);
  let body = options.body;

  if (options.form && body && typeof body === "object") {
    body = new URLSearchParams(body);
  } else if (body && typeof body === "object") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  if (token) headers["Authorization"] = "Bearer " + token;

  let resp;
  try {
    resp = await fetch(API_BASE + path, { ...options, headers, body });
  } catch (e) {
    throw new Error("Не удалось связаться с сервером: " + e.message);
  }

  if (resp.status === 401) {
    clearSession();
    if (!location.pathname.endsWith("login.html")) {
      window.location.href = "login.html";
    }
    throw new Error("Сессия истекла, войдите заново");
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (_e) {
      /* тело не JSON — оставляем statusText */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (resp.status === 204) return null;
  const text = await resp.text();
  return text ? JSON.parse(text) : null;
}

const ROLE_LABELS = {
  employee: "Сотрудник",
  commander: "Командир отделения",
  staff: "Штаб",
  admin: "Сисадмин",
};

// Должны совпадать со списком CATEGORIES/CATEGORY_LABELS в backend/app/ai.py.
const CATEGORY_LABELS = {
  atd: "Административное/бытовое происшествие",
  fire: "Пожар",
  traffic_accident: "ДТП",
  explosion: "Взрыв",
  shooting: "Стрельба",
  drone: "Удар БПЛА",
  medical: "Медицинский случай",
  other: "Иное",
};
const CATEGORY_COLORS = {
  atd: "#98a2b8",
  fire: "#e63946",
  traffic_accident: "#d99a2b",
  explosion: "#b5179e",
  shooting: "#7209b7",
  drone: "#3a86ff",
  medical: "#3fb37f",
  other: "#6c757d",
};

// Поля шаблона, которые подставляются кодом (см. backend/app/routers/reports.py),
// а не ИИ — сотруднику их лучше не редактировать вручную на превью рапорта.
const SYSTEM_TEMPLATE_FIELDS = ["date", "officer_name", "unit_name", "category_label", "location"];

// Та же логика подстановки, что render_template в backend/app/ai.py —
// используется для мгновенного превью на клиенте при правке полей,
// без повторного похода на сервер.
function renderTemplateClient(templateHtml, fields) {
  return templateHtml.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_m, key) => {
    const val = fields[key] ?? "";
    return escapeHtml(val).replace(/\n/g, "<br>");
  });
}

// Куда вести пользователя сразу после входа / при попытке открыть страницу
// не по роли.
const ROLE_HOME = {
  employee: "report.html",
  commander: "map.html",
  staff: "map.html",
  admin: "map.html",
};

// Проверяет токен, подтягивает актуального пользователя и (если передан
// список ролей) редиректит, если роль не подходит. Возвращает пользователя.
async function requireAuth(allowedRoles) {
  if (!getToken()) {
    window.location.href = "login.html";
    throw new Error("no token");
  }
  const user = await apiFetch("/auth/me");
  setUser(user);
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    window.location.href = ROLE_HOME[user.role] || "login.html";
    throw new Error("role not allowed on this page");
  }
  return user;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// Рисует общую шапку с навигацией и текущим пользователем в элемент #opsNav.
function renderNav(user, activePage) {
  const nav = document.getElementById("opsNav");
  if (!nav) return;

  const links = [{ href: "report.html", label: "Подать рапорт", key: "report" }];
  if (["commander", "staff", "admin"].includes(user.role)) {
    links.push({ href: "map.html", label: "Карта", key: "map" });
  }
  if (user.role === "admin") {
    links.push({ href: "admin.html", label: "Админка", key: "admin" });
  }

  const linksHtml = links
    .map(
      (l) =>
        `<a href="${l.href}" class="${l.key === activePage ? "active" : ""}">${l.label}</a>`
    )
    .join("");

  nav.innerHTML = `
    <div class="nav-brand">TMap · Служебный модуль</div>
    <div class="nav-links">${linksHtml}</div>
    <div class="nav-user">
      <span>${escapeHtml(user.full_name || user.username)} · ${ROLE_LABELS[user.role] || user.role}</span>
      <button id="logoutBtn" class="btn-secondary">Выйти</button>
    </div>
  `;
  document.getElementById("logoutBtn").addEventListener("click", logout);
}
