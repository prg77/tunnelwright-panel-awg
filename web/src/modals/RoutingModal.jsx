import React, { useState, useEffect } from "react";
import { api } from "../api";
import { Btn } from "../components/ui";
import { flag } from "../utils/countries";

const MODES = [
  ["all",     "Весь трафик"],
  ["include", "Только выбранные"],
  ["exclude", "Всё, кроме выбранных"],
];
const lbl = {fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:6};
const PREVIEW_LINES = 40;

// ─── Режим + выбор списков ───────────────────────────────────────
const Section = ({ title, hint, mode, setMode, lists, selected, setSelected, empty }) => (
  <div style={{display:"flex",flexDirection:"column",gap:8}}>
    <div style={lbl}>{title}</div>
    <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
      {MODES.map(([m, label]) => (
        <button key={m} onClick={() => setMode(m)} style={{padding:"6px 10px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:12,fontWeight:600,
          border:`1px solid ${mode===m?"var(--cyan)":"var(--border)"}`,background:mode===m?"var(--surface2)":"transparent",
          color:mode===m?"var(--cyan)":"var(--muted)"}}>{label}</button>
      ))}
    </div>
    {mode !== "all" && (lists.length === 0
      ? <div style={{fontSize:12,color:"var(--warning)"}}>{empty}</div>
      : <div style={{display:"flex",flexDirection:"column",gap:2,maxHeight:170,overflowY:"auto",border:"1px solid var(--border)",borderRadius:"var(--radius)",padding:4}}>
          {lists.map(l => (
            <label key={l.id} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 8px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:14,
              background:selected.includes(l.id)?"var(--surface2)":"transparent"}}>
              <input type="checkbox" checked={selected.includes(l.id)}
                onChange={e => setSelected(e.target.checked ? [...selected, l.id] : selected.filter(x => x !== l.id))}/>
              <span style={{flex:1}}>{l.name}</span>
              <span style={{fontSize:12,color:"var(--muted)"}}>
                {l.kind === "net"
                  ? [l.countries.slice(0, 5).map(flag).join(""), l.cidrs.length ? `${l.cidrs.length} подсет.` : ""].filter(Boolean).join(" ")
                  : `${l.apps.length} шт.`}
              </span>
            </label>
          ))}
        </div>)}
    {hint && mode !== "all" && <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.5}}>{hint}</div>}
  </div>
);

// ─── RoutingModal — какие сети и приложения клиента идут через VPN ──
export const RoutingModal = ({ client, push, setPage, onSaved, onClose }) => {
  const [r, setR] = useState(null);
  const [lists, setLists] = useState([]);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    Promise.all([api.routing(client.id), api.lists()])
      .then(([rt, ls]) => { setR(rt); setLists(ls); })
      .catch(e => { push({type:"err", title:"Маршрутизация", detail:e.message}); onClose(); });
  }, [client.id]); // push/onClose — стабильные колбэки родителя

  const upd = (k) => (v) => { setR(x => ({...x, [k]: v})); setPreview(null); };

  const save = async () => {
    setBusy(true);
    try {
      await api.saveRouting(client.id, r);
      onSaved?.();
      push({type:"ok", title:"Маршрутизация сохранена", detail:"Выдайте клиенту конфиг заново (QR или файл)"});
      setPreview(await api.routingPreview(client.id));
    } catch (e) { push({type:"err", title:"Не сохранено", detail:e.message}); }
    finally { setBusy(false); }
  };

  const toLists = () => { onClose(); setPage("lists"); };
  const pvLines = preview ? preview.config.split("\n") : [];

  return (
    <div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(8px)",zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:22,maxWidth:540,width:"100%",animation:"pop .22s ease",maxHeight:"94vh",overflowY:"auto",display:"flex",flexDirection:"column",gap:16}} onClick={e => e.stopPropagation()}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <div style={{flex:1}}>
            <div style={{fontWeight:700,fontSize:15}}>⇄ Маршрутизация</div>
            <div style={{fontSize:12,color:"var(--muted)"}}>{client.label} · <span style={{fontFamily:"var(--mono)"}}>{(client.ip||"").replace("/32","")}{client.uid?` · #${client.uid}`:""}</span></div>
          </div>
          <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:19}}>✕</button>
        </div>

        {!r ? <div style={{padding:30,textAlign:"center",color:"var(--muted)",fontSize:14}}>Загрузка…</div> : <>
          <Section title="Сети" mode={r.net_mode} setMode={upd("net_mode")} selected={r.net_lists} setSelected={upd("net_lists")}
            lists={lists.filter(l => l.kind === "net")}
            empty={<>Списков сетей нет — <a onClick={toLists} style={{color:"var(--cyan)",cursor:"pointer"}}>создайте в справочнике</a></>}
            hint={r.net_mode === "include"
              ? "AllowedIPs = подсети из списков (+ DNS-серверы). Работает в любом клиенте WireGuard/AmneziaWG."
              : "AllowedIPs = весь трафик, исключения — #@ws:DisallowedIPs. Исключения понимает только WireSock."}/>
          <Section title="Приложения (WireSock)" mode={r.app_mode} setMode={upd("app_mode")} selected={r.app_lists} setSelected={upd("app_lists")}
            lists={lists.filter(l => l.kind === "app")}
            empty={<>Списков приложений нет — <a onClick={toLists} style={{color:"var(--cyan)",cursor:"pointer"}}>создайте в справочнике</a></>}
            hint={r.app_mode === "include" ? "#@ws:AllowedApps — через VPN идут только эти приложения." : "#@ws:DisallowedApps — эти приложения идут мимо VPN."}/>
          <div>
            <div style={lbl}>Свои параметры конфига</div>
            <textarea value={r.extra} onChange={e => upd("extra")(e.target.value)} rows={4} spellCheck={false}
              placeholder={"Параметр = значение — заменит или добавит строку:\n#@ws:Socks5Proxy = 127.0.0.1:1080\nJc = 6\nPersistentKeepalive =   ← пустое значение удаляет"}
              style={{background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",padding:"7px 10px",
                fontSize:12,width:"100%",boxSizing:"border-box",fontFamily:"var(--mono)",resize:"vertical"}}/>
            <div style={{fontSize:12,color:"var(--muted)",marginTop:4,lineHeight:1.5}}>
              Секция определяется автоматически (Jc, MTU, DNS… — [Interface], остальное — [Peer]); заголовок [Interface] или [Peer] задаёт её явно.
            </div>
          </div>

          {preview && (
            <div style={{border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",overflow:"hidden"}}>
              <div style={{padding:"8px 12px",fontSize:12,display:"flex",gap:12,flexWrap:"wrap",background:"var(--surface2)"}}>
                {preview.allowed != null && <span>AllowedIPs: <b>{preview.allowed}</b></span>}
                {preview.disallowed > 0 && <span>DisallowedIPs: <b>{preview.disallowed}</b></span>}
                {preview.apps > 0 && <span>приложений: <b>{preview.apps}</b></span>}
                <span>размер: <b>{(preview.size / 1024).toFixed(1)} КБ</b></span>
                <span style={{color:preview.qr?"var(--success)":"var(--warning)"}}>{preview.qr ? "QR ✓" : "QR не поместится — отдайте файл"}</span>
              </div>
              <pre style={{margin:0,padding:"8px 12px",fontSize:12,fontFamily:"var(--mono)",maxHeight:220,overflow:"auto",whiteSpace:"pre-wrap",wordBreak:"break-all"}}>
                {pvLines.slice(0, PREVIEW_LINES).map(l => l.length > 300 ? l.slice(0, 300) + " …" : l).join("\n")}
                {pvLines.length > PREVIEW_LINES ? "\n…" : ""}
              </pre>
            </div>
          )}

          <div style={{display:"flex",gap:8,justifyContent:"flex-end"}}>
            <Btn v="ghost" onClick={onClose}>Закрыть</Btn>
            <Btn v="primary" onClick={save} disabled={busy}>{busy ? "Сохранение…" : "Сохранить"}</Btn>
          </div>
        </>}
      </div>
    </div>
  );
};
