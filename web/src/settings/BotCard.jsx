import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

const COMMANDS = [
  ["/status", "состояние сервера"], ["/clients", "список клиентов"], ["/client имя", "карточка клиента"],
  ["/conf имя", "конфиг и QR"], ["/link имя", "ссылка на страницу"], ["/add имя [дней]", "новый клиент"], ["/enable имя", "включить"],
  ["/disable имя", "отключить"], ["/backup", "бэкап сейчас"],
];

// ─── BotCard — Telegram-бот администратора ────────────────────
export const BotCard = ({ push }) => {
  const [bot, setBot] = useState(null);
  useEffect(() => { api.bot().then(setBot).catch(() => {}); }, []);
  if (!bot) return null;

  const toggle = async () => {
    try {
      setBot(await api.setBot(!bot.enabled));
      push({type: bot.enabled ? "warn" : "ok", title: bot.enabled ? "Бот выключен" : "Бот включён",
            detail: bot.enabled ? "" : "Напишите боту /help из чата администратора"});
    } catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
  };

  return (
    <Card>
      <CardH sub="управление из Telegram — команды принимаются только из чата администратора">Telegram-бот</CardH>
      <div style={{padding:"12px 18px",display:"flex",flexDirection:"column",gap:12}}>
        <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
          <span style={{fontSize:14,flex:1}}>
            {bot.configured
              ? <>Бот использует токен и Chat ID из настроек Telegram выше. {bot.enabled
                  ? <b style={{color:"var(--success)"}}>Включён</b> : <span style={{color:"var(--muted)"}}>Выключен</span>}</>
              : <span style={{color:"var(--warning)"}}>Сначала укажите токен бота и Chat ID в настройках Telegram</span>}
          </span>
          <Btn v={bot.enabled ? "danger" : "primary"} disabled={!bot.configured} onClick={toggle}>
            {bot.enabled ? "Выключить" : "Включить"}
          </Btn>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:"4px 16px",fontSize:12}}>
          {COMMANDS.map(([c, d]) => (
            <div key={c}><code style={{fontFamily:"var(--mono)",color:"var(--cyan)"}}>{c}</code> <span style={{color:"var(--muted)"}}>— {d}</span></div>
          ))}
        </div>
      </div>
    </Card>
  );
};
