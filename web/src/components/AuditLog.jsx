import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "./ui";
import { fmtDateTime } from "../utils/time";

// Действия администраторов (журнал на сервере, panel-api /api/audit)
const ACTIONS = {
  login:"Вход", login_failed:"Неудачный вход", password_changed:"Смена пароля",
  totp_enabled:"2FA включена", totp_disabled:"2FA отключена", settings_changed:"Настройки",
  client_created:"Устройство добавлено", client_deleted:"Устройство удалено", client_enabled:"Устройство включено",
  client_disabled:"Устройство отключено", client_address:"Смена IP", client_renamed:"Устройство переименовано", client_expiry:"Срок доступа",
  user_created:"Пользователь создан", user_deleted:"Пользователь удалён", user_enabled:"Пользователь включён",
  user_disabled:"Пользователь отключён", user_renamed:"Пользователь переименован", user_expiry:"Срок доступа",
  user_expired:"Срок истёк", users_merged:"Пользователи объединены", user_link_created:"Ссылка создана",
  client_expired:"Срок истёк", limits_changed:"Лимиты", traffic_reset:"Сброс статистики",
  telegram_settings:"Telegram", portal_name:"Имя панели", node_down:"Нода недоступна", node_up:"Нода восстановлена",
  node_install_started:"Установка ноды", node_installed:"Нода установлена", node_update_started:"Обновление ноды",
  node_updated:"Нода обновлена", node_update_failed:"Обновление ноды не удалось", node_remove_started:"Удаление ноды", node_removed:"Нода удалена", node_renamed:"Нода переименована",
  nodes_pending:"Ноды недоступны", client_routing:"Маршрутизация", client_config_sent:"Конфиг отправлен",
  group_created:"Группа создана", group_updated:"Группа изменена", group_deleted:"Группа удалена", groups_reordered:"Порядок групп",
  list_created:"Список создан", list_updated:"Список изменён", list_deleted:"Список удалён", geoip_refresh:"GeoIP",
  backup_run:"Бэкап", backup_download:"Бэкап скачан", backup_settings:"Настройки бэкапа",
  backup_restore:"Восстановлено из бэкапа", backup_restore_failed:"Восстановление не выполнено",
  quota_set:"Квота", quota_exceeded:"Квота превышена", quota_reset:"Квота сброшена",
  user_link_sent:"Ссылка отправлена", user_link_regenerated:"Новая ссылка", user_link_revoked:"Ссылка отозвана",
  user_config_download:"Конфиг по ссылке", user_page_settings:"Страница пользователя", telegram_bot:"Telegram-бот",
  admin_reset:"Сброс администратора",
};
const WARN = new Set(["login_failed","client_deleted","user_deleted","traffic_reset","node_down","totp_disabled","client_expired","user_expired",
  "node_removed","node_update_failed","quota_exceeded","nodes_pending","user_link_revoked","admin_reset"]);

export const AuditLog = () => {
  const [rows, setRows] = useState([]);
  const [more, setMore] = useState(true);
  const load = async (before) => {
    try {
      const r = await api.audit(before);
      setRows(prev => before ? [...prev, ...r] : r);
      setMore(r.length === 100);
    } catch { setMore(false); }
  };
  useEffect(() => { load(); }, []);

  const details = (r) => {
    const d = r.details || {};
    return Object.entries(d).filter(([,v]) => v !== null && v !== undefined && v !== "")
      .map(([k,v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
  };

  return (
    <Card>
      <CardH sub="кто, когда и что менял — хранится на сервере">Действия администраторов</CardH>
      <div style={{padding:"6px 0"}}>
        {rows.length === 0 && <div style={{padding:"12px 18px",fontSize:14,color:"var(--muted)"}}>Записей пока нет</div>}
        {rows.map(r => (
          <div key={r.id} style={{display:"grid",gridTemplateColumns:"120px 1fr",gap:10,padding:"7px 18px",
            borderTop:"1px solid var(--border)",fontSize:14}}>
            <span style={{color:"var(--muted)",fontFamily:"var(--mono)",fontSize:12}}>{fmtDateTime(r.ts*1000)}</span>
            <span>
              <b style={{color:WARN.has(r.action)?"var(--error)":"var(--text)"}}>{ACTIONS[r.action]||r.action}</b>
              {r.target && <span style={{color:"var(--muted)"}}> · {r.target}</span>}
              <span style={{color:"var(--muted)"}}> · {r.admin||"—"}{r.ip ? ` · ${r.ip}` : ""}</span>
              {details(r) && <div style={{color:"var(--muted)",fontSize:12,marginTop:2,wordBreak:"break-word"}}>{details(r)}</div>}
            </span>
          </div>
        ))}
        {more && rows.length > 0 && (
          <div style={{padding:"10px 18px"}}><Btn onClick={()=>load(rows[rows.length-1].id)}>Показать ещё</Btn></div>
        )}
      </div>
    </Card>
  );
};
