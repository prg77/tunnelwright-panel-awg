import { api } from "../api";
import { dayKey } from "../utils/time";

// Трафик по клиентам считает сервер (panel-api, раз в минуту). Браузер только читает его
// и кэширует в localStorage, чтобы статистика сразу показывалась при открытии панели.
// Structure: { [clientId]: { name, prev, daily: {"2026-03-17": {tx,rx}} } }
export const CU_KEY = "awg-client-usage";

export const clientUsageStore = {
  load: () => { try { return JSON.parse(localStorage.getItem(CU_KEY) || "{}"); } catch { return {}; } },
  save: (d) => { try { localStorage.setItem(CU_KEY, JSON.stringify(d)); } catch {} },
  clear: () => { try { localStorage.removeItem(CU_KEY); } catch {} },

  loadFromServer: async () => {
    try {
      const data = await api.trafficUsage();
      if (!data || typeof data !== "object") return null;
      clientUsageStore.save(data);
      return data;
    } catch { return null; }
  },

  // "YYYY-MM-DD" в часовом поясе панели — те же границы суток, что и на сервере
  dayKey,

  // Суммарный трафик клиента за период [fromDay, toDay] включительно
  sumForClient: (data, id, fromDay, toDay) => {
    const rec = data[id];
    if (!rec) return 0;
    let total = 0;
    for (const [d, v] of Object.entries(rec.daily || {})) {
      if (d >= fromDay && d <= toDay) total += (v.tx || 0) + (v.rx || 0);
    }
    return total;
  },

  // Топ-N клиентов за период, возвращает [{id, name, bytes}]
  topN: (data, n, fromDay, toDay) => {
    return Object.entries(data)
      .map(([id, rec]) => ({
        id, name: rec.name,
        bytes: clientUsageStore.sumForClient(data, id, fromDay, toDay)
      }))
      .filter(x => x.bytes > 0)
      .sort((a, b) => b.bytes - a.bytes)
      .slice(0, n);
  },
};
