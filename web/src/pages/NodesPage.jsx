import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

const inp = {background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",
             padding:"7px 10px",fontSize:14,width:"100%",boxSizing:"border-box",fontFamily:"var(--sans)"};
const lbl = {fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:5};
const Field = ({ label, children, style }) => <div style={style}><div style={lbl}>{label}</div>{children}</div>;
const fmtDate = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("ru") : "—";
// Автообновление агента: нода догоняет версию панели сама (юнит systemd на ноде)
const updText = (n) => {
  const u = n.update, last = u.last;
  if (!u.auto) return "вручную — обновите один раз кнопкой «Обновить», дальше автоматически";
  if (u.current) return last?.ok ? `автоматически · ${last.message}` : "автоматически · версия актуальна";
  if (last && !last.ok && last.version === u.target) return `не удалось: ${last.message} — повтор через 30 мин`;
  return u.pending ? `обновляется до ${u.target}…` : `ожидает обновления до ${u.target}`;
};

// ─── Форма установки / обновления ноды ───────────────────────────
const InstallForm = ({ node, mode, push, onStarted, onCancel, onPanelOnly }) => {
  const upd = mode === "update", rm = mode === "remove";
  const [f, setF] = useState({name:"", host:"", ssh_port:node?.ssh_port || 22, wg_port:51820, agent_port:8711, wg_dns:"1.1.1.1"});
  const [auth, setAuth] = useState("password");
  const [secret, setSecret] = useState({password:"", private_key:"", passphrase:""});
  const [busy, setBusy] = useState(false);
  const [reinst, setReinst] = useState({new_host_key:false, restore:false});
  const [archive, setArchive] = useState(null);   // бэкап с данными этой ноды
  useEffect(() => { if (upd) api.nodeBackup(node.id).then(r => setArchive(r.archive)).catch(() => {}); }, [upd, node]);
  const set = (k) => (e) => setF(x => ({...x, [k]: e.target.value}));
  const setS = (k) => (e) => setSecret(x => ({...x, [k]: e.target.value}));

  const submit = async () => {
    const creds = auth === "password" ? {password: secret.password} : {private_key: secret.private_key, passphrase: secret.passphrase || null};
    setBusy(true);
    try {
      const body = upd ? {ssh_port: +f.ssh_port || null, ...reinst, ...creds}
                       : {...f, ssh_port:+f.ssh_port, wg_port:+f.wg_port, agent_port:+f.agent_port, ...creds};
      const job = rm ? await api.removeNode(node.id, creds) : upd ? await api.updateNode(node.id, body) : await api.installNode(body);
      setSecret({password:"", private_key:"", passphrase:""});   // секреты не держим в состоянии
      onStarted(job);
    } catch (e) { push({type:"err", title:"Не запущено", detail:e.message}); }
    finally { setBusy(false); }
  };
  const ready = (upd || rm || f.host.trim()) && (auth === "password" ? secret.password : secret.private_key.trim());

  return (
    <Card>
      <CardH sub={rm ? "контейнеры VPN и агента, их данные и правило брандмауэра; Docker остаётся"
                 : upd ? "новая версия агента; токен, сертификат и клиенты ноды сохраняются"
                      : "Debian или Ubuntu, доступ root по SSH; VPN и агент ставятся в Docker"}>
        {rm ? `Удалить ноду «${node.name}»` : upd ? `Обновить ноду «${node.name}»` : "Новая нода"}
      </CardH>
      <div style={{padding:"14px 18px",display:"flex",flexDirection:"column",gap:12}}>
        {!upd && !rm && <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:10}}>
          <Field label="Название"><input value={f.name} onChange={set("name")} placeholder="Финляндия" maxLength={64} style={inp}/></Field>
          <Field label="Адрес сервера (IP или домен)"><input value={f.host} onChange={set("host")} placeholder="203.0.113.10" style={inp}/></Field>
          <Field label="Порт VPN (UDP)"><input type="number" value={f.wg_port} onChange={set("wg_port")} style={inp}/></Field>
          <Field label="Порт агента (TCP)"><input type="number" value={f.agent_port} onChange={set("agent_port")} style={inp}/></Field>
          <Field label="DNS для клиентов"><input value={f.wg_dns} onChange={set("wg_dns")} style={inp}/></Field>
        </div>}
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:10}}>
          {!rm && <Field label="SSH-порт"><input type="number" value={f.ssh_port} onChange={set("ssh_port")} style={inp}/></Field>}
          <Field label="Вход root">
            <div style={{display:"flex",gap:4}}>
              {[["password","Пароль"],["key","Ключ SSH"]].map(([k, l]) => (
                <button key={k} onClick={() => setAuth(k)} style={{flex:1,padding:"7px 0",borderRadius:"var(--radius)",cursor:"pointer",fontSize:12,fontWeight:600,
                  border:`1px solid ${auth===k?"var(--cyan)":"var(--border)"}`,background:auth===k?"var(--surface2)":"transparent",
                  color:auth===k?"var(--cyan)":"var(--muted)"}}>{l}</button>))}
            </div>
          </Field>
        </div>
        {upd && <div style={{display:"flex",flexDirection:"column",gap:6,fontSize:14}}>
          <label style={{display:"flex",gap:8,alignItems:"flex-start",cursor:"pointer"}}>
            <input type="checkbox" checked={reinst.new_host_key} onChange={e => setReinst(x => ({...x, new_host_key:e.target.checked}))} style={{marginTop:4}}/>
            <span>Сервер переустановлен — принять новый ключ SSH-хоста<br/><span style={{fontSize:12,color:"var(--muted)"}}>иначе панель откажется подключаться, если ключ изменился</span></span>
          </label>
          <label style={{display:"flex",gap:8,alignItems:"flex-start",cursor:archive?"pointer":"not-allowed",opacity:archive?1:.6}}>
            <input type="checkbox" disabled={!archive} checked={reinst.restore} onChange={e => setReinst(x => ({...x, restore:e.target.checked}))} style={{marginTop:4}}/>
            <span>Восстановить данные ноды из бэкапа<br/><span style={{fontSize:12,color:"var(--muted)"}}>
              {archive ? `ключи сервера и клиентов из  — клиентам не придётся менять конфиги; изменения после бэкапа будут потеряны`
                       : "в бэкапах панели нет данных этой ноды (нужен пароль бэкапа и хотя бы один архив)"}</span></span>
          </label>
        </div>}
        {auth === "password"
          ? <Field label="Пароль root"><input type="password" autoComplete="off" value={secret.password} onChange={setS("password")} style={inp}/></Field>
          : <>
              <Field label="Приватный ключ (OpenSSH или PEM)">
                <textarea value={secret.private_key} onChange={setS("private_key")} rows={5} spellCheck={false} autoComplete="off"
                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" style={{...inp,fontFamily:"var(--mono)",fontSize:12,resize:"vertical"}}/>
              </Field>
              <Field label="Пароль ключа (если есть)"><input type="password" autoComplete="off" value={secret.passphrase} onChange={setS("passphrase")} style={inp}/></Field>
            </>}
        <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
          {rm ? <>Профили клиентов на этой ноде ({node.clients}) будут удалены — сами клиенты останутся на других нодах.
                  Пароль и ключ используются один раз и не сохраняются.</>
              : <>Пароль и ключ используются один раз для установки и не сохраняются. Панель запомнит отпечаток ключа
                  SSH-сервера и сертификат агента; агент будет принимать запросы только с IP этой панели.</>}
        </div>
        <div style={{display:"flex",gap:8,justifyContent:"flex-end"}}>
          {rm && <Btn v="ghost" onClick={onPanelOnly} style={{marginRight:"auto"}} title="Сервер недоступен или VPN на нём нужно оставить">Только из панели</Btn>}
          <Btn v="ghost" onClick={onCancel}>Отмена</Btn>
          <Btn v={rm ? "danger" : "primary"} onClick={submit} disabled={busy || !ready}>{busy ? "Запуск…" : rm ? "Удалить с сервера" : upd ? "Обновить" : "Установить"}</Btn>
        </div>
      </div>
    </Card>
  );
};

// ─── Ход установки ───────────────────────────────────────────────
const ACTION = {install:"установка", update:"обновление", remove:"удаление с сервера"};
const JobLog = ({ job, onClose }) => {
  const box = useRef(null);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [job.log.length]);
  const color = job.status === "ok" ? "var(--success)" : job.status === "error" ? "var(--error)" : "var(--cyan)";
  return (
    <Card>
      <CardH right={job.status !== "running" && <Btn v="ghost" onClick={onClose} style={{height:28}}>Закрыть</Btn>}
        sub={`${job.host} · ${ACTION[job.action] || job.action}`}>
        <span style={{color}}>{job.status === "running" ? "⏳" : job.status === "ok" ? "✓" : "✗"}</span> {job.name}
      </CardH>
      <pre ref={box} style={{margin:0,padding:"10px 18px",fontSize:12,fontFamily:"var(--mono)",maxHeight:280,overflow:"auto",
        whiteSpace:"pre-wrap",wordBreak:"break-word",lineHeight:1.5}}>
        {job.log.join("\n") || "…"}
      </pre>
    </Card>
  );
};

// ─── Карточка ноды ───────────────────────────────────────────────
const NodeCard = ({ n, onUpdate, onDelete, onRename }) => {
  const [name, setName] = useState(n.name);
  const m = n.metrics;
  const row = (k, v) => v != null && v !== "" && <div style={{display:"flex",gap:10,fontSize:12,padding:"3px 0"}}>
    <span style={{color:"var(--muted)",minWidth:120}}>{k}</span><span style={{fontFamily:"var(--mono)",wordBreak:"break-all"}}>{v}</span></div>;
  return (
    <Card>
      <div style={{padding:"12px 18px",display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",borderBottom:"1px solid var(--border)"}}>
        <span title={n.ok ? "работает" : n.error || "недоступна"} style={{width:9,height:9,borderRadius:"50%",background:n.ok?"var(--success)":"var(--error)",flexShrink:0}}/>
        <input value={name} onChange={e => setName(e.target.value)} maxLength={64}
          onBlur={() => name.trim() && name !== n.name && onRename(name.trim())}
          onKeyDown={e => e.key === "Enter" && e.target.blur()}
          style={{...inp,width:"auto",flex:"1 1 160px",fontWeight:600,fontSize:14,background:"transparent",border:"1px solid transparent"}}/>
        {n.is_local && <span style={{fontSize:11,padding:"2px 7px",borderRadius:"var(--radius)",background:"var(--surface2)",color:"var(--muted)",fontWeight:700}}>ПАНЕЛЬ</span>}
        <span style={{fontSize:12,color:"var(--muted)"}}>профилей: {n.clients}</span>
        {!n.is_local && <div style={{display:"flex",gap:4}}>
          <Btn v="ghost" onClick={onUpdate} title="Обновить агент ноды по SSH" style={{height:28,padding:"0 10px"}}>Обновить</Btn>
          <Btn v="danger" onClick={onDelete} title="Удалить ноду" style={{height:28,padding:"0 9px"}}>✕</Btn>
        </div>}
      </div>
      <div style={{padding:"8px 18px 12px"}}>
        {!n.ok && <div style={{fontSize:12,color:"var(--error)",padding:"4px 0"}}>{n.error || "нет ответа"}</div>}
        {m && <div style={{display:"flex",gap:16,fontSize:12,padding:"4px 0 6px",flexWrap:"wrap"}}>
          <span>CPU <b>{m.cpu}%</b></span><span>RAM <b>{m.ram_pct}%</b></span><span>Диск <b>{m.disk_pct}%</b></span>
        </div>}
        {row("Адрес VPN", n.host ? `${n.host}:${n.wg_port}` : null)}
        {row("Версия агента", n.version)}
        {!n.is_local && n.update && row("Обновление", updText(n))}
        {m && row("Торренты", !m.torrent_block ? "агент без блокировки — обновите ноду"
          : m.torrent_block.active ? `блокируются · отброшено пакетов: ${m.torrent_block.blocked ?? 0}` : `не блокируются: ${m.torrent_block.error}`)}
        {!n.is_local && row("Агент", `TCP ${n.agent_port}`)}
        {!n.is_local && row("Установлена", fmtDate(n.installed_at))}
        {row("Сертификат агента", n.cert_sha256 ? `SHA-256 ${n.cert_sha256.match(/.{1,2}/g).slice(0, 8).join(":")}…` : null)}
        {row("Ключ SSH-сервера", n.ssh_host_key)}
      </div>
    </Card>
  );
};

// ─── Страница «Ноды» ─────────────────────────────────────────────
export const NodesPage = ({ push, setConfirmModal }) => {
  const [list, setList] = useState(null);
  const [form, setForm] = useState(null);   // null | "new" | нода
  const [job, setJob] = useState(null);

  const load = useCallback(() => api.nodes().then(setList).catch(e => push({type:"err", title:"Ноды", detail:e.message})), [push]);
  useEffect(() => {
    load();
    api.nodeJobs().then(js => { const r = js.find(j => j.status === "running"); if (r) setJob(r); }).catch(() => {});
  }, [load]);

  // Ход установки: опрос, пока задача идёт
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(async () => {
      try {
        const j = await api.nodeJob(job.id);
        setJob(j);
        if (j.status !== "running") {
          load();
          push(j.status === "ok" ? {type:"ok", title:j.action === "remove" ? "Нода удалена" : "Нода готова", detail:j.name}
                                 : {type:"err", title:j.action === "remove" ? "Удаление не удалось" : "Установка не удалась", detail:j.error});
        }
      } catch { /* панель перезапускается — следующий опрос */ }
    }, 1500);
    return () => clearInterval(t);
  }, [job, load, push]);

  const panelOnly = (n) => setConfirmModal({
    title: `Убрать ноду «${n.name}» только из панели?`,
    detail: `Профили клиентов на этой ноде (${n.clients}) забудутся — сами клиенты останутся на других нодах. На сервере VPN продолжит работать: `
          + "удалить его можно вручную (docker compose -f /opt/tunnelwright-node/docker-compose.yml down -v).",
    confirmLabel: "Убрать",
    onConfirm: async () => {
      try { await api.delNode(n.id); push({type:"warn", title:"Нода убрана", detail:n.name}); load(); }
      catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
    },
  });
  const rename = async (n, name) => {
    try { await api.renameNode(n.id, name); load(); } catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
  };

  return (
    <div className="wide-page" style={{width:"100%",maxWidth:780,display:"flex",flexDirection:"column",gap:14,margin:"0 auto"}}>
      <div style={{display:"flex",gap:8,alignItems:"center"}}>
        <span style={{fontSize:12,color:"var(--muted)",flex:1,lineHeight:1.6}}>
          VPN-серверы под этой панелью. Каждый клиент получает профиль на всех нодах с одним IP — пользователь выбирает сервер в приложении.
        </span>
        <Btn v="ghost" onClick={load} title="Обновить">⟳</Btn>
        <Btn v="primary" onClick={() => setForm("new")} disabled={job?.status === "running"}>Добавить ноду</Btn>
      </div>
      {job && <JobLog job={job} onClose={() => setJob(null)}/>}
      {form && <InstallForm key={form === "new" ? "new" : `${form.mode}-${form.node.id}`} node={form === "new" ? null : form.node}
        mode={form === "new" ? "install" : form.mode} push={push}
        onStarted={(j) => { setForm(null); setJob(j); }} onCancel={() => setForm(null)}
        onPanelOnly={() => { const n = form.node; setForm(null); panelOnly(n); }}/>}
      {list === null && <div style={{fontSize:14,color:"var(--muted)",padding:20}}>Загрузка…</div>}
      {(list || []).map(n => (
        <NodeCard key={`${n.id}-${n.name}`} n={n} onUpdate={() => setForm({node:n, mode:"update"})} onDelete={() => setForm({node:n, mode:"remove"})} onRename={(name) => rename(n, name)}/>
      ))}
    </div>
  );
};
