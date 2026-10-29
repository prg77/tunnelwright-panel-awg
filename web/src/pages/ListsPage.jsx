import React, { useState, useEffect, useMemo, useCallback } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";
import { COUNTRIES, countryName, flag } from "../utils/countries";

const inp = {background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",
             padding:"7px 10px",fontSize:14,width:"100%",boxSizing:"border-box",fontFamily:"var(--sans)"};
const lbl = {fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:5};
const lines = (t) => t.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);

// 1 страна, 2 страны, 5 стран
const plural = (n, one, few, many) => {
  const d = n % 10, h = n % 100;
  return `${n} ${d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many}`;
};
const summary = (l) => l.kind === "net"
  ? [l.countries.length && plural(l.countries.length, "страна", "страны", "стран"),
     l.cidrs.length && plural(l.cidrs.length, "подсеть", "подсети", "подсетей")].filter(Boolean).join(" · ") || "пусто"
  : plural(l.apps.length, "запись", "записи", "записей");

// ─── Выбор стран: поиск + выбранные чипами ──────────────────────
const CountryPicker = ({ value, onChange }) => {
  const [q, setQ] = useState("");
  const all = useMemo(() => COUNTRIES(), []);
  const found = q.trim()
    ? all.filter(c => !value.includes(c.code) &&
        (c.name.toLowerCase().includes(q.toLowerCase()) || c.code === q.trim().toLowerCase())).slice(0, 8)
    : [];
  return (
    <div>
      <div style={{display:"flex",gap:5,flexWrap:"wrap",marginBottom:value.length?8:0}}>
        {value.map(cc => (
          <span key={cc} style={{display:"inline-flex",alignItems:"center",gap:5,padding:"3px 8px",borderRadius:"var(--radius)",
            fontSize:12,background:"var(--surface2)",border:"1px solid var(--border)"}}>
            {flag(cc)} {countryName(cc)}
            <button onClick={() => onChange(value.filter(x => x !== cc))} title="Убрать"
              style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",padding:0,fontSize:14}}>✕</button>
          </span>
        ))}
      </div>
      <div style={{position:"relative"}}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Найти страну: Россия, de, Китай…" style={inp}
          onKeyDown={e => { if (e.key === "Enter" && found[0]) { onChange([...value, found[0].code]); setQ(""); } }}/>
        {found.length > 0 && (
          <div style={{position:"absolute",zIndex:5,left:0,right:0,top:"100%",marginTop:3,background:"var(--surface)",
            border:"1px solid var(--border)",borderRadius:"var(--radius)",overflow:"hidden",boxShadow:"0 6px 18px rgba(0,0,0,.25)"}}>
            {found.map(c => (
              <button key={c.code} onClick={() => { onChange([...value, c.code]); setQ(""); }}
                style={{display:"flex",width:"100%",gap:8,padding:"7px 10px",background:"none",border:"none",
                  color:"var(--text)",cursor:"pointer",fontSize:14,textAlign:"left"}}>
                <span>{flag(c.code)}</span><span style={{flex:1}}>{c.name}</span>
                <span style={{fontFamily:"var(--mono)",color:"var(--muted)"}}>{c.code.toUpperCase()}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Редактор списка ─────────────────────────────────────────────
const ListEditor = ({ kind, list, push, onDone }) => {
  const [name, setName] = useState(list?.name || "");
  const [countries, setCountries] = useState(list?.countries || []);
  const [cidrs, setCidrs] = useState((list?.cidrs || []).join("\n"));
  const [apps, setApps] = useState((list?.apps || []).join("\n"));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const body = kind === "net" ? {name, countries, cidrs: lines(cidrs)} : {name, apps: apps.split("\n").map(s=>s.trim()).filter(Boolean)};
    setBusy(true);
    try {
      const saved = list ? await api.updateList(list.id, body) : await api.addList({kind, ...body});
      push({type:"ok", title: list ? "Список сохранён" : "Список создан", detail: saved.name});
      onDone(true);
    } catch (e) { push({type:"err", title:"Не сохранено", detail:e.message}); }
    finally { setBusy(false); }
  };

  return (
    <Card>
      <CardH sub={kind === "net"
        ? "страны (база ipdeny.com, обновляется раз в неделю) и свои подсети IPv4"
        : "процессы (chrome.exe, telegram) и папки (C:\\Games\\) — параметры WireSock"}>
        {list ? `✎ ${list.name}` : kind === "net" ? "Новый список сетей" : "Новый список приложений"}
      </CardH>
      <div style={{padding:"14px 18px",display:"flex",flexDirection:"column",gap:12}}>
        <div><div style={lbl}>Название</div>
          <input value={name} onChange={e => setName(e.target.value)} maxLength={64} style={inp}
            placeholder={kind === "net" ? "Например: Россия + банки" : "Например: Браузеры"}/></div>
        {kind === "net" ? <>
          <div><div style={lbl}>Страны</div><CountryPicker value={countries} onChange={setCountries}/></div>
          <div><div style={lbl}>Подсети и адреса</div>
            <textarea value={cidrs} onChange={e => setCidrs(e.target.value)} rows={6} spellCheck={false}
              placeholder={"по одной в строке:\n10.0.0.0/8\n203.0.113.5"} style={{...inp,fontFamily:"var(--mono)",resize:"vertical"}}/></div>
        </> : (
          <div><div style={lbl}>Приложения и папки</div>
            <textarea value={apps} onChange={e => setApps(e.target.value)} rows={8} spellCheck={false}
              placeholder={"по одному в строке:\nchrome\nfirefox.exe\nC:\\Games\\"} style={{...inp,fontFamily:"var(--mono)",resize:"vertical"}}/></div>
        )}
        <div style={{display:"flex",gap:8,justifyContent:"flex-end"}}>
          <Btn v="ghost" onClick={() => onDone(false)}>Отмена</Btn>
          <Btn v="primary" onClick={save} disabled={busy || !name.trim()}>{busy ? "Сохранение…" : "Сохранить"}</Btn>
        </div>
      </div>
    </Card>
  );
};

// ─── GeoIP: кэш стран ────────────────────────────────────────────
const GeoipCard = ({ push, version }) => {
  const [geo, setGeo] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.geoip().then(setGeo).catch(() => {}); }, [version]);
  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api.geoipRefresh();
      setGeo(g => ({...g, countries: r.countries}));
      const errs = Object.keys(r.errors || {});
      push(errs.length ? {type:"warn", title:"GeoIP обновлён частично", detail:`Ошибки: ${errs.join(", ").toUpperCase()}`}
                       : {type:"ok", title:"GeoIP обновлён"});
    } catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
    finally { setBusy(false); }
  };
  const entries = Object.entries(geo?.countries || {});
  return (
    <Card>
      <CardH sub={`подсети стран из ${geo?.source || "ipdeny.com"}; используемые страны обновляются автоматически раз в неделю`}
        right={<Btn v="ghost" onClick={refresh} disabled={busy || !entries.length}>{busy ? "Обновление…" : "Обновить"}</Btn>}>
        GeoIP
      </CardH>
      <div style={{padding:"10px 18px",fontSize:14}}>
        {!entries.length
          ? <span style={{color:"var(--muted)"}}>Страны ещё не загружались — добавьте страну в список сетей.</span>
          : <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(210px,1fr))",gap:"4px 16px"}}>
              {entries.map(([cc, s]) => (
                <div key={cc} style={{display:"flex",gap:6}}>
                  <span>{flag(cc)} {countryName(cc)}</span>
                  <span style={{marginLeft:"auto",fontFamily:"var(--mono)",color:"var(--muted)",fontSize:12}}>
                    {s.count} · {new Date(s.updated * 1000).toLocaleDateString("ru")}
                  </span>
                </div>))}
            </div>}
      </div>
    </Card>
  );
};

// ─── Страница «Списки» ───────────────────────────────────────────
export const ListsPage = ({ push, setConfirmModal, onChanged }) => {
  const [kind, setKind] = useState("net");
  const [items, setItems] = useState(null);
  const [edit, setEdit] = useState(null);     // null | "new" | список
  const [version, setVersion] = useState(0);

  const load = useCallback(() => api.lists().then(setItems).catch(e => push({type:"err", title:"Списки", detail:e.message})), [push]);
  useEffect(() => { load(); }, [load]);

  const done = (changed) => { setEdit(null); if (changed) { load(); setVersion(v => v + 1); onChanged?.(); } };
  const dup = async (l) => {
    try { const c = await api.dupList(l.id); push({type:"ok", title:"Копия создана", detail:c.name}); load(); }
    catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
  };
  const del = (l) => setConfirmModal({
    title: `Удалить список «${l.name}»?`,
    detail: l.clients.length
      ? `Список выбран у клиентов: ${l.clients.length}. Он будет убран из их маршрутизации — проверьте их конфиги.`
      : "Список не используется клиентами.",
    onConfirm: async () => {
      try { await api.delList(l.id); push({type:"ok", title:"Список удалён", detail:l.name}); load(); onChanged?.(); }
      catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
    },
  });

  const shown = (items || []).filter(l => l.kind === kind);
  const tab = (k, label) => (
    <button onClick={() => { setKind(k); setEdit(null); }} style={{padding:"7px 14px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:14,fontWeight:600,
      border:`1px solid ${kind===k?"var(--cyan)":"var(--border)"}`,background:kind===k?"var(--surface2)":"transparent",
      color:kind===k?"var(--cyan)":"var(--muted)"}}>{label}</button>
  );

  return (
    <div className="wide-page" style={{width:"100%",maxWidth:780,display:"flex",flexDirection:"column",gap:14,margin:"0 auto"}}>
      <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
        {tab("net", "Сети")}{tab("app", "Приложения")}
        <Btn v="primary" onClick={() => setEdit("new")} style={{marginLeft:"auto"}}>Новый список</Btn>
      </div>
      <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
        Списки выбираются в маршрутизации клиента (кнопка ⇄ на странице «Клиенты»): весь трафик, только сети из списков
        или всё, кроме них. Исключения сетей и списки приложений понимает клиент <b>WireSock</b>; режим «только списки»
        для сетей работает в любом клиенте WireGuard/AmneziaWG.
      </div>
      {edit && <ListEditor key={edit === "new" ? `new-${kind}` : edit.id} kind={kind} list={edit === "new" ? null : edit} push={push} onDone={done}/>}
      <Card>
        {items === null && <div style={{padding:"20px 18px",fontSize:14,color:"var(--muted)"}}>Загрузка…</div>}
        {items && !shown.length && <div style={{padding:"28px 18px",textAlign:"center",fontSize:14,color:"var(--muted)"}}>
          Списков {kind === "net" ? "сетей" : "приложений"} пока нет</div>}
        {shown.map(l => (
          <div key={l.id} style={{display:"flex",alignItems:"center",gap:10,padding:"10px 18px",borderBottom:"1px solid var(--border)",flexWrap:"wrap"}}>
            <div style={{flex:"1 1 220px",minWidth:0}}>
              <div style={{fontWeight:600,fontSize:14}}>{l.name}</div>
              <div style={{fontSize:12,color:"var(--muted)",marginTop:2}}>
                {l.kind === "net" && l.countries.length > 0 && <span style={{marginRight:6}}>{l.countries.slice(0, 8).map(flag).join(" ")}{l.countries.length > 8 ? " …" : ""}</span>}
                {summary(l)} · {l.clients.length ? `клиентов: ${l.clients.length}` : "не используется"}
              </div>
            </div>
            <div style={{display:"flex",gap:4}}>
              <Btn v="ghost" onClick={() => setEdit(l)} title="Изменить" style={{height:28,padding:"0 9px"}}>✎</Btn>
              <Btn v="ghost" onClick={() => dup(l)} title="Дублировать" style={{height:28,padding:"0 9px"}}>⧉</Btn>
              <Btn v="danger" onClick={() => del(l)} title="Удалить" style={{height:28,padding:"0 9px"}}>✕</Btn>
            </div>
          </div>
        ))}
      </Card>
      {kind === "net" && <GeoipCard push={push} version={version}/>}
    </div>
  );
};
