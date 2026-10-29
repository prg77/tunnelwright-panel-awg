// Часовой пояс панели — из настроек сервера (config.timezone), по умолчанию Москва.
// Используется для часов, отметок времени в уведомлениях и границ суток в статистике.
let panelTz = "Europe/Moscow";

export const setPanelTz = (tz) => { if (tz) panelTz = tz; };
export const getPanelTz = () => panelTz;

export const fmtDateTime = (d) => new Date(d).toLocaleString("ru", { timeZone: panelTz });
export const fmtClock = () => new Date().toLocaleTimeString("ru",
  { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: panelTz });

// "YYYY-MM-DD" в часовом поясе панели (en-CA даёт ISO-порядок)
export const dayKey = (ts) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: panelTz, year: "numeric", month: "2-digit", day: "2-digit" })
    .format(new Date(ts));
