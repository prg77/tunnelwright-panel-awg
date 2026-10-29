import React, { useState, useEffect } from "react";
import { api } from "../api";

const copyText = (t) => {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
  const e = document.createElement("textarea");
  e.value = t; e.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(e); e.select();
  try { document.execCommand("copy"); } catch { /* старый браузер */ }
  document.body.removeChild(e);
  return Promise.resolve();
};

const small = {padding:"5px 9px",borderRadius:"var(--radius)",fontSize:12,fontWeight:600,cursor:"pointer",
               background:"var(--surface2)",border:"1px solid var(--border)",color:"var(--muted)"};

// ─── Личная ссылка клиента на страницу пользователя (/u/<токен>) ──
export const UserLink = ({ client }) => {
  const [token, setToken] = useState(undefined);   // undefined — загрузка, null — ссылки нет
  const [enabled, setEnabled] = useState(true);
  const [msg, setMsg] = useState("");
  const [confirmRegen, setConfirmRegen] = useState(false);

  useEffect(() => {
    let dead = false;
    Promise.all([api.userLinks(), api.userPage()])
      .then(([links, page]) => { if (!dead) { setToken(links[client.id]?.token || null); setEnabled(page.enabled); } })
      .catch(e => { if (!dead) { setToken(null); setMsg(e.message); } });
    return () => { dead = true; };
  }, [client.id]);

  const url = token ? `${window.location.origin}/u/${token}` : "";
  const flash = (t) => { setMsg(t); setTimeout(() => setMsg(""), 2500); };
  const issue = async (regenerate) => {
    try {
      const r = await api.issueLink(client.id, regenerate);
      setToken(r.token); setConfirmRegen(false);
      await copyText(`${window.location.origin}${r.path}`);
      flash(regenerate ? "Новая ссылка скопирована — старая больше не работает" : "Ссылка создана и скопирована");
    } catch (e) { flash(e.message); }
  };
  const revoke = async () => {
    try { await api.revokeLink(client.id); setToken(null); flash("Ссылка отозвана"); }
    catch (e) { flash(e.message); }
  };

  if (token === undefined) return null;
  return (
    <div style={{marginBottom:14,background:"var(--bg)",borderRadius:"var(--radius-lg)",padding:"10px 12px"}}>
      <div style={{fontSize:11,color:"var(--muted)",fontWeight:700,marginBottom:8}}>
        Страница пользователя
      </div>
      {!enabled && <div style={{fontSize:12,color:"var(--warning)",marginBottom:6}}>Выключена в настройках — ссылки не открываются</div>}
      {token ? <>
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          <input readOnly value={url} onFocus={e => e.target.select()}
            style={{flex:1,minWidth:0,background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",
              color:"var(--text)",padding:"6px 8px",fontSize:12,fontFamily:"var(--mono)"}}/>
          <button onClick={() => copyText(url).then(() => flash("Скопировано"))} style={{...small,color:"var(--cyan)"}}>⧉</button>
        </div>
        <div style={{display:"flex",gap:6,marginTop:7,flexWrap:"wrap"}}>
          <a href={url} target="_blank" rel="noreferrer" style={{...small,textDecoration:"none"}}>Открыть ↗</a>
          {confirmRegen
            ? <button onClick={() => issue(true)} style={{...small,color:"var(--warning)",borderColor:"color-mix(in srgb,var(--warning) 40%,transparent)"}}>Точно заменить?</button>
            : <button onClick={() => setConfirmRegen(true)} style={small}>Новая ссылка</button>}
          <button onClick={revoke} style={{...small,color:"var(--error)"}}>Отозвать</button>
        </div>
      </> : (
        <button onClick={() => issue(false)} style={{...small,width:"100%",padding:"8px 0",color:"var(--cyan)",fontSize:12}}>
          Создать ссылку для пользователя
        </button>
      )}
      <div style={{fontSize:12,color:"var(--muted)",marginTop:7,lineHeight:1.5}}>
        {msg || "Пользователь сам скачает конфиг и QR по ссылке, без входа в панель. Сертификат самоподписанный — браузер попросит подтвердить переход."}
      </div>
    </div>
  );
};
