import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";
import { fmtBytes } from "../utils/format";
import { fmtDateTime } from "../utils/time";

const field = {background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",
  fontSize:14,padding:"8px 12px"};
const SCHEDULES = [["off","Выключено"],["daily","Каждый день"],["weekly","Раз в неделю"]];

// ─── BackupCard — серверные бэкапы: ключи VPN + данные панели, AES-256, Telegram ──
export const BackupCard = ({ push, setConfirmModal }) => {
  const [data, setData] = useState(null);          // {settings, files, restore}
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [rFile, setRFile] = useState(null);         // восстановление: архив и его пароль
  const [rPass, setRPass] = useState("");
  const [rBusy, setRBusy] = useState(false);
  const load = () => api.backups().then(setData).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!data) return null;
  const s = data.settings;

  const save = async (patch) => {
    try {
      const next = await api.saveBackupSettings(patch);
      setData(d => ({...d, settings: next}));
      if (patch.password) { setPassword(""); push({type:"ok", title:"Пароль бэкапа сохранён"}); }
    } catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
  };
  const runNow = async () => {
    setBusy(true);
    try {
      const r = await api.runBackup();
      push({type:"ok", title:"Бэкап создан", detail:`${r.file} · ${fmtBytes(r.size)}${r.telegram ? " · отправлен в Telegram" : ""}`});
      load();
    } catch (e) { push({type:"err", title:"Бэкап не создан", detail:e.message}); }
    finally { setBusy(false); }
  };
  const doRestore = async () => {
    setRBusy(true);
    try {
      const r = await api.restoreBackup(rFile, rPass);
      push({type:"ok", title:"Бэкап принят — панель перезапускается",
        detail:`версия ${r.version||"?"} от ${r.created ? fmtDateTime(r.created*1000) : "?"}`
          + (r.nodes.length ? ` · ноды: ${r.nodes.join(", ")}` : "")
          + (r.local_dropped ? " · VPN старого сервера панели здесь не используется" : "")
          + ". Войдите с логином и паролем из бэкапа."});
      setTimeout(() => window.location.reload(), 8000);
    } catch (e) { push({type:"err", title:"Восстановление не выполнено", detail:e.message}); setRBusy(false); }
  };
  const askRestore = () => setConfirmModal({
    title:"Восстановить панель из бэкапа?",
    detail:`Клиенты, ноды, настройки, журнал и учётка администратора будут заменены данными из ${rFile.name}. `
      + "Текущая база сохранится как panel.db.before-restore.",
    confirmLabel:"Восстановить", onConfirm:doRestore,
  });

  return (
    <Card>
      <CardH sub="ключи VPN, клиенты, лимиты, статистика и настройки — архив зашифрован паролем">Резервные копии</CardH>
      <div style={{padding:"12px 18px",display:"flex",flexDirection:"column",gap:14}}>
        <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
          <span style={{fontSize:14,minWidth:130}}>Пароль бэкапа {s.password_set
            ? <span style={{color:"var(--success)"}}>· задан</span> : <span style={{color:"var(--error)"}}>· не задан</span>}</span>
          <input type="password" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}
            placeholder={s.password_set ? "Новый пароль (от 8 символов)" : "Пароль (от 8 символов)"} style={{...field, flex:1, minWidth:180}}/>
          <Btn v="primary" disabled={password.length < 8} onClick={()=>save({password})}>Сохранить</Btn>
        </div>
        <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
          Без пароля архив не создаётся: в нём приватные ключи всех клиентов. Сохраните пароль отдельно — без него
          бэкап не открыть. Архив открывается 7-Zip{data.restore ? "; восстановить — ниже" : <>; восстановление на сервере: <code style={{fontFamily:"var(--mono)"}}>tunnelwright restore файл.zip</code></>}
        </div>

        <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
          <span style={{fontSize:14,minWidth:130}}>Автоматически</span>
          <select value={s.schedule} onChange={e=>save({schedule:e.target.value})} style={field}>
            {SCHEDULES.map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <span style={{fontSize:14,color:"var(--muted)"}}>в</span>
          <select value={s.hour} onChange={e=>save({hour:Number(e.target.value)})} style={field} disabled={s.schedule==="off"}>
            {Array.from({length:24},(_,h)=><option key={h} value={h}>{String(h).padStart(2,"0")}:00</option>)}
          </select>
          <label style={{display:"flex",alignItems:"center",gap:6,fontSize:14,cursor:"pointer"}}>
            <input type="checkbox" checked={s.telegram} onChange={e=>save({telegram:e.target.checked})}/>
            отправлять в Telegram
          </label>
        </div>

        <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
          <Btn v="primary" disabled={busy || !s.password_set} onClick={runNow}>{busy ? "Создаю…" : "Сделать бэкап сейчас"}</Btn>
          {s.last_ts && <span style={{fontSize:12,color:s.last_ok?"var(--muted)":"var(--error)"}}>
            Последний: {fmtDateTime(s.last_ts*1000)} · {s.last_ok ? "успешно" : `ошибка: ${s.last_error}`}
          </span>}
        </div>

        {data.files.length > 0 && <div>
          <div style={{fontSize:12,color:"var(--muted)",marginBottom:6}}>На сервере (последние 5):</div>
          {data.files.map(f => (
            <div key={f.name} style={{display:"flex",gap:10,alignItems:"center",padding:"6px 0",borderTop:"1px solid var(--border)",fontSize:14}}>
              <span style={{fontFamily:"var(--mono)",flex:1,wordBreak:"break-all"}}>{f.name}</span>
              <span style={{color:"var(--muted)"}}>{fmtBytes(f.size)}</span>
              <a href={api.backupUrl(f.name)} download style={{color:"var(--cyan)",textDecoration:"none"}}>Скачать</a>
            </div>
          ))}
        </div>}

        {data.restore && <div style={{borderTop:"1px solid var(--border)",paddingTop:12,display:"flex",flexDirection:"column",gap:8}}>
          <div style={{fontSize:14,fontWeight:500}}>Восстановить из бэкапа</div>
          <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
            <input type="file" accept=".zip,application/zip" onChange={e=>setRFile(e.target.files[0]||null)}
              style={{fontSize:14,color:"var(--muted)",flex:1,minWidth:200}}/>
            <input type="password" autoComplete="off" value={rPass} onChange={e=>setRPass(e.target.value)}
              placeholder="Пароль архива" style={{...field, flex:1, minWidth:160}}/>
            <Btn v="danger" disabled={!rFile || !rPass || rBusy} onClick={askRestore}>{rBusy ? "Восстанавливаю…" : "Восстановить"}</Btn>
          </div>
          <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
            Перенос панели на этот сервер: данные панели заменяются архивом, удалённые ноды подключатся сами.
            Если нода отвечает «только с прежнего IP панели» — Ноды → Обновить (по SSH).
          </div>
        </div>}
      </div>
    </Card>
  );
};
