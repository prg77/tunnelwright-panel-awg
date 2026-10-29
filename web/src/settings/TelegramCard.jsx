import React, { useState, useEffect } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

// ─── TelegramCard — уведомления администратору ────────────────────
// Сообщения отправляет сервер по выбранным событиям. Токен бота хранится только на сервере:
// интерфейс видит лишь, что он задан, и последние 4 символа; пустое поле — оставить прежний.
const EVENT_DEFS = [
  {key:"on_start",       label:"Панель запущена",                     desc:"после старта или обновления панели"},
  {key:"on_client_add",  label:"Новый клиент — сообщение, .conf и QR", desc:"конфиг каждой ноды отправляется в чат"},
  {key:"on_client_del",  label:"Клиент удалён",                       desc:""},
  {key:"on_toggle",      label:"Клиент включён / отключён",           desc:""},
  {key:"on_limit_set",   label:"Лимит скорости установлен",           desc:""},
  {key:"on_limit_del",   label:"Лимит скорости снят",                 desc:""},
  {key:"on_health_fail", label:"Нода недоступна",                     desc:"проверка раз в 2 минуты, без повторов"},
  {key:"on_health_ok",   label:"Нода восстановлена",                  desc:""},
];

export const TelegramCard = ({ push }) => {
  const [s, setS] = useState(null);              // настройки с сервера
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [events, setEvents] = useState({});
  const [busy, setBusy] = useState("");

  const apply = (r) => { setS(r); setChatId(r.chat_id || ""); setEvents(r.events || {}); setToken(""); };
  useEffect(() => { api.telegram().then(apply).catch(e => push({type:"err", title:"Telegram", detail:e.message})); }, [push]);

  const save = async (patch, okTitle) => {
    setBusy("save");
    try {
      apply(await api.saveTelegram(patch));
      if (okTitle) push({type:"ok", title:okTitle});
      return true;
    } catch (e) { push({type:"err", title:"Не сохранено", detail:e.message}); return false; }
    finally { setBusy(""); }
  };
  const form = () => ({chat_id:chatId.trim(), events, ...(token.trim() ? {token:token.trim()} : {})});
  const test = async () => {
    if (!(await save(form()))) return;
    setBusy("test");
    try { await api.testTelegram(); push({type:"ok", title:"Тест успешен", detail:"Сообщение доставлено в Telegram"}); }
    catch (e) { push({type:"err", title:"Тест не прошёл", detail:e.message}); }
    finally { setBusy(""); }
  };

  if (!s) return <Card><CardH>Telegram</CardH><div style={{padding:16,color:"var(--muted)"}}>Загрузка…</div></Card>;
  const ready = (s.token_set || token.trim()) && chatId.trim();
  return (
    <Card>
      <CardH sub={s.active ? `уведомления активны · событий: ${Object.values(s.events).filter(Boolean).length}` : "уведомления выключены"}
        right={<label style={{display:"flex",alignItems:"center",gap:8,fontSize:14,cursor:ready?"pointer":"not-allowed"}}>
          <input type="checkbox" checked={s.enabled} disabled={!ready || !!busy}
            onChange={e => save({...form(), enabled:e.target.checked}, e.target.checked ? "Уведомления включены" : "Уведомления выключены")}/>
          Включены
        </label>}>
        Telegram
      </CardH>
      <form onSubmit={e => { e.preventDefault(); save(form(), "Telegram сохранён"); }} autoComplete="off"
        style={{padding:"12px 16px",display:"flex",flexDirection:"column",gap:12}}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))",gap:12}}>
          <label className="field"><span>Токен бота</span>
            <input type="password" value={token} onChange={e => setToken(e.target.value)} autoComplete="new-password"
              placeholder={s.token_set ? `задан (…${s.token_hint}) — пусто: не менять` : "получить у @BotFather → /newbot"}
              style={{fontFamily:"var(--mono)"}}/>
          </label>
          <label className="field"><span>Chat ID</span>
            <input value={chatId} onChange={e => setChatId(e.target.value)} placeholder="числовой ID чата или @канал"/>
          </label>
        </div>
        <div>
          <div style={{fontSize:14,fontWeight:500,marginBottom:4}}>События</div>
          {EVENT_DEFS.map(({key, label, desc}) => (
            <label key={key} style={{display:"flex",gap:10,alignItems:"flex-start",padding:"6px 0",cursor:"pointer",borderBottom:"1px solid var(--border)"}}>
              <input type="checkbox" checked={!!events[key]} onChange={() => setEvents(x => ({...x, [key]:!x[key]}))} style={{marginTop:4}}/>
              <span style={{fontSize:14}}>{label}{desc && <span style={{display:"block",fontSize:12,color:"var(--muted)"}}>{desc}</span>}</span>
            </label>
          ))}
        </div>
        <div style={{display:"flex",gap:8}}>
          <Btn v="primary" type="submit" disabled={!!busy}>{busy === "save" ? "Сохранение…" : "Сохранить"}</Btn>
          <Btn v="ghost" onClick={test} disabled={!!busy || !ready}>{busy === "test" ? "Отправка…" : "Тест"}</Btn>
        </div>
      </form>
    </Card>
  );
};
