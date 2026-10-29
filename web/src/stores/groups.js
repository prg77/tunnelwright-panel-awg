import { useSyncExternalStore } from "react";
import { api } from "../api";

// ─── Группы клиентов (с сервера) ─────────────────────────────────
// Один кэш на приложение: фильтр клиентов, карточка клиента, добавление и настройки
// видят одни и те же группы и обновляются вместе после правки.
export const NO_GROUP = "Без группы";
const NO_GROUP_COLOR = "#8e8e9e";

let state = { list: [], names: [NO_GROUP], colors: { [NO_GROUP]: NO_GROUP_COLOR } };
const subs = new Set();

const set = (list) => {
  state = {
    list,
    names: [NO_GROUP, ...list.map(g => g.name)],
    colors: { [NO_GROUP]: NO_GROUP_COLOR, ...Object.fromEntries(list.map(g => [g.name, g.color])) },
  };
  subs.forEach(f => f());
};

export const groupsStore = {
  reload: () => api.groups().then(set).catch(() => {}),
  set,
};

export const useGroups = () => useSyncExternalStore(
  (f) => { subs.add(f); return () => subs.delete(f); },
  () => state,
);
