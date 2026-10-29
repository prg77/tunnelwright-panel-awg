export const api = {
  async req(method, path, body) {
    const opts = { method, credentials:"same-origin", headers:{"Content-Type":"application/json",Accept:"application/json"} };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch("/api" + path, opts);
    if (r.status === 204) return null;
    if (!r.ok) {
      // panel-api (FastAPI): {"detail": "текст"} или {"detail": {"need_totp": true, "message": …}}
      let msg = r.statusText, detail = null;
      try { const j = await r.json(); detail = j.detail; msg = (typeof detail === "string" ? detail : detail?.message) || j.error || msg; } catch {}
      const err = new Error(msg);
      err.status = r.status;
      err.needTotp = !!(detail && typeof detail === "object" && detail.need_totp);
      throw err;
    }
    const ct = r.headers.get("content-type")||"";
    return ct.includes("application/json") ? r.json() : r.text();
  },
  session: ()    => api.req("GET",    "/auth/session"),
  login:   (username, password, totp) => api.req("POST", "/auth/login", {username, password, ...(totp ? {totp} : {})}),
  logout:  ()    => api.req("POST",   "/auth/logout"),
  // Безопасность и настройки панели
  changePassword: (current, next) => api.req("POST", "/auth/password", {current, new: next}),
  totpSetup:   ()        => api.req("POST", "/auth/totp/setup"),
  totpEnable:  (code)    => api.req("POST", "/auth/totp/enable", {code}),
  totpDisable: (code, password) => api.req("POST", "/auth/totp/disable", {code, password}),
  settings:    ()        => api.req("GET",  "/settings"),
  saveSettings:(patch)   => api.req("PUT",  "/settings", patch),
  timezones:   ()        => api.req("GET",  "/timezones"),
  audit:       (beforeId) => api.req("GET", `/audit?limit=100${beforeId ? `&before_id=${beforeId}` : ""}`),
  // Квоты трафика (ГБ за календарный месяц)
  quotas:      ()        => api.req("GET",  "/quotas"),
  setQuota:    (id, gb)  => api.req("PUT",  `/clients/${id}/quota`, {limit_gb: gb || null}),
  // Группы клиентов
  groups:      ()        => api.req("GET",    "/groups"),
  addGroup:    (g)       => api.req("POST",   "/groups", g),
  updateGroup: (id, g)   => api.req("PUT",    `/groups/${id}`, g),
  orderGroups: (ids)     => api.req("PUT",    "/groups-order", ids),
  delGroup:    (id)      => api.req("DELETE", `/groups/${id}`),
  // Справочник списков (сети и приложения) и GeoIP
  lists:       (kind)    => api.req("GET",    `/lists${kind ? `?kind=${kind}` : ""}`),
  addList:     (l)       => api.req("POST",   "/lists", l),
  updateList:  (id, l)   => api.req("PUT",    `/lists/${id}`, l),
  dupList:     (id)      => api.req("POST",   `/lists/${id}/duplicate`),
  delList:     (id)      => api.req("DELETE", `/lists/${id}`),
  geoip:       ()        => api.req("GET",    "/geoip"),
  geoipRefresh:()        => api.req("POST",   "/geoip/refresh"),
  // Маршрутизация клиента (WireSock)
  routingAll:  ()        => api.req("GET",    "/routing"),
  routing:     (id)      => api.req("GET",    `/clients/${id}/routing`),
  saveRouting: (id, r)   => api.req("PUT",    `/clients/${id}/routing`, r),
  routingPreview: (id)   => api.req("GET",    `/clients/${id}/routing/preview`),
  // Ноды
  nodes:       ()        => api.req("GET",    "/nodes"),
  installNode: (b)       => api.req("POST",   "/nodes/install", b),
  updateNode:  (id, b)   => api.req("POST",   `/nodes/${id}/update`, b),
  removeNode:  (id, b)   => api.req("POST",   `/nodes/${id}/remove`, b),
  nodeBackup:  (id)      => api.req("GET",    `/nodes/${id}/backup`),
  nodeJobs:    ()        => api.req("GET",    "/nodes/jobs"),
  nodeJob:     (jid)     => api.req("GET",    `/nodes/jobs/${jid}`),
  renameNode:  (id, name) => api.req("PUT",   `/nodes/${id}`, {name}),
  delNode:     (id)      => api.req("DELETE", `/nodes/${id}`),
  // Страница пользователя (/u/<токен>)
  userPage:    ()        => api.req("GET",    "/user-page"),
  saveUserPage:(s)       => api.req("PUT",    "/user-page", s),
  previewUserPage: (template) => api.req("POST", "/user-page/preview", {template}),
  userLinks:   ()        => api.req("GET",    "/user-links"),
  issueLink:   (id, regenerate) => api.req("POST", `/clients/${id}/link${regenerate ? "?regenerate=true" : ""}`),
  revokeLink:  (id)      => api.req("DELETE", `/clients/${id}/link`),
  // Бэкапы
  backups:     ()        => api.req("GET",  "/backups"),
  saveBackupSettings: (s) => api.req("PUT", "/backups/settings", s),
  runBackup:   ()        => api.req("POST", "/backups/run"),
  backupUrl:   (name)    => `/api/backups/file/${encodeURIComponent(name)}`,
  // Тело — сам архив; пароль в заголовке (encodeURIComponent: заголовки только latin-1)
  restoreBackup: async (file, password) => {
    const r = await fetch(`/api/backups/restore?name=${encodeURIComponent(file.name)}`, {method:"POST", credentials:"same-origin",
      headers:{"Content-Type":"application/zip", "X-Backup-Password":encodeURIComponent(password)}, body:file});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((typeof j.detail === "string" && j.detail) || r.statusText);
    return j;
  },
  // Telegram-бот
  bot:         ()        => api.req("GET",  "/telegram/bot"),
  setBot:      (enabled) => api.req("PUT",  "/telegram/bot", {enabled}),
  // Клиенты: профиль на каждой ноде с одним IP; трафик и handshake — по всем нодам
  clients:     ()        => api.req("GET",    "/clients"),
  createClient:(c)       => api.req("POST",   "/clients", c),          // {name, ip?, expiresAt?, group?, note?, limit?}
  patchClient: (id, p)   => api.req("PATCH",  `/clients/${id}`, p),    // {name?, ip?, enabled?, expiresAt?, group?, note?}
  delClient:   (id)      => api.req("DELETE", `/clients/${id}`),
  setLimit:    (id, l)   => api.req("PUT",    `/clients/${id}/limit`, l),  // {down, up} Мбит/с
  delLimit:    (id)      => api.req("DELETE", `/clients/${id}/limit`),
  sendConfig:  (id, node) => api.req("POST",  `/clients/${id}/telegram${node ? `?node=${node}` : ""}`),
  // Конфиг и QR — профиль клиента на ноде (без node — первая нода)
  qr:      async (id, node) => {
    const r = await fetch(`/api/clients/${id}/qr.svg${node ? `?node=${node}` : ""}`, {credentials:"same-origin"});
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
    return r.text();
  },
  confUrl: (id, node) => `/api/clients/${id}/config${node ? `?node=${node}` : ""}`,
  // Дашборд
  stats:          ()     => api.req("GET",    "/stats"),
  trafficHistory: ()     => api.req("GET",    "/traffic/history"),
  trafficUsage:   ()     => api.req("GET",    "/traffic/usage"),
  resetTraffic:   ()     => api.req("DELETE", "/traffic"),
  portalName:     ()     => api.req("GET",    "/portal-name"),
  // Telegram: уведомления отправляет сервер; токен бота в браузер не отдаётся
  telegram:     ()       => api.req("GET",  "/telegram"),
  saveTelegram: (s)      => api.req("PUT",  "/telegram", s),           // {enabled?, token?, chat_id?, events?}
  testTelegram: ()       => api.req("POST", "/telegram/test"),
};

