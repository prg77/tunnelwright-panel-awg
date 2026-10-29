import { api } from "../api";

// ─── История трафика для графика ───────────────────────────────────
// Точки раз в минуту пишет сервер (panel-api). Браузер дополняет их живыми точками
// между опросами сервера и кэширует в localStorage, чтобы график сразу показывался.
export const TH_KEY = "awg-traffic-history";
export const TH_MAX = 60 * 24 * 31; // 31 день по 1 точке/мин

const save = (pts) => { try { localStorage.setItem(TH_KEY, JSON.stringify(pts.slice(-TH_MAX))); } catch {} };

export const thStore = {
  load: () => { try { return JSON.parse(localStorage.getItem(TH_KEY) || "[]"); } catch { return []; } },
  clear: () => { try { localStorage.removeItem(TH_KEY); } catch {} },
  push: (ts, tx, rx) => {
    const pts = thStore.load();
    const last = pts[pts.length - 1];
    if (last && ts - last.ts < 2500) return pts;
    pts.push({ ts, tx, rx });
    save(pts);
    return pts;
  },
  // Сервер — источник правды; локальные точки остаются только новее последней серверной
  loadFromServer: async () => {
    try {
      const srv = await api.trafficHistory();
      if (!Array.isArray(srv)) return null;
      const lastSrvTs = srv.length > 0 ? srv[srv.length - 1].ts : 0;
      const merged = [...srv, ...thStore.load().filter(p => p.ts > lastSrvTs + 60000)].slice(-TH_MAX);
      save(merged);
      return merged;
    } catch { return null; }
  },
};
