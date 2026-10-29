import React from "react";
import { bareIp, freeIps, validIp } from "../utils/ip";

// ─── IpField — адрес устройства в подсети панели ─────────────────
// Пустое поле — следующий свободный адрес (подставит сервер); ниже — ближайшие свободные.
export const IpField = ({ value, onChange, used, subnet, current, onEnter }) => {
  const free = freeIps(used, subnet, 6);
  const ip = bareIp(value);
  const taken = ip && ip !== current && (used || []).map(bareIp).includes(ip);
  const bad = ip && !validIp(ip, subnet);
  const err = bad ? `Адрес должен быть в ${subnet} (кроме первого и адресов на .0 и .255)` : taken ? "Адрес уже занят" : "";
  return (
    <div>
      <input value={value} onChange={e => onChange(e.target.value.trim())} inputMode="decimal" spellCheck={false}
        placeholder={current || (free[0] ? `${free[0]} — следующий свободный` : "свободных адресов нет")}
        onKeyDown={e => e.key === "Enter" && onEnter && onEnter()}
        className={err ? "invalid" : ""} style={{width:"100%",fontFamily:"var(--mono)"}}/>
      <div style={{fontSize:12,color:err ? "var(--error)" : "var(--muted)",marginTop:5,display:"flex",gap:6,flexWrap:"wrap",alignItems:"center"}}>
        {err || <>
          <span>Подсеть {subnet}. Свободные:</span>
          {free.map(f => (
            <button key={f} type="button" onClick={() => onChange(f)}
              style={{background:"none",border:"none",padding:0,cursor:"pointer",fontFamily:"var(--mono)",fontSize:12,
                color:f === ip ? "var(--text)" : "var(--cyan)"}}>{f}</button>
          ))}
        </>}
      </div>
    </div>
  );
};

export const ipError = (value, used, subnet, current) => {
  const ip = bareIp(value);
  if (!ip) return "";
  if (!validIp(ip, subnet)) return "неверный адрес";
  if (ip !== current && (used || []).map(bareIp).includes(ip)) return "адрес уже занят";
  return "";
};
