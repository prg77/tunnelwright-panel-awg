import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

const Toggle = ({ on, onClick, children }) => (
  <button onClick={onClick} style={{display:"inline-flex",alignItems:"center",gap:8,background:"none",border:"none",
    color:"var(--text)",cursor:"pointer",fontSize:14,padding:0}}>
    <span style={{width:30,height:17,borderRadius:"var(--radius)",background:on?"var(--cyan)":"var(--surface2)",border:"1px solid var(--border)",
      position:"relative",transition:"background .15s"}}>
      <span style={{position:"absolute",top:1,left:on?14:1,width:13,height:13,borderRadius:"50%",background:"#fff",transition:"left .15s"}}/>
    </span>
    {children}
  </button>
);

// ─── UserPageCard — страница пользователя и её шаблон ────────────
export const UserPageCard = ({ push }) => {
  const [s, setS] = useState(null);
  const [tpl, setTpl] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState("");
  const area = useRef(null);

  useEffect(() => { api.userPage().then(r => { setS(r); setTpl(r.template); }).catch(() => {}); }, []);
  if (!s) return null;

  const save = async (patch, okTitle) => {
    setBusy(true);
    try {
      const r = await api.saveUserPage(patch);
      setS(r); setTpl(r.template);
      push({type:"ok", title: okTitle});
    } catch (e) { push({type:"err", title:"Не сохранено", detail:e.message}); }
    finally { setBusy(false); }
  };
  const insert = (key) => {
    const el = area.current, ph = `{${key}}`;
    if (!el) { setTpl(t => t + ph); return; }
    const a = el.selectionStart, b = el.selectionEnd;
    setTpl(t => t.slice(0, a) + ph + t.slice(b));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = a + ph.length; });
  };
  const showPreview = async () => {
    try { setPreview((await api.previewUserPage(tpl)).html); }
    catch (e) { push({type:"err", title:"Предпросмотр", detail:e.message}); }
  };
  const dirty = tpl !== s.template;

  return (
    <Card>
      <CardH sub="личная ссылка клиента: статус, срок, трафик, QR и файл конфига — без входа в панель">Страница пользователя</CardH>
      <div style={{padding:"12px 18px",display:"flex",flexDirection:"column",gap:12}}>
        <div style={{display:"flex",gap:20,flexWrap:"wrap"}}>
          <Toggle on={s.enabled} onClick={() => save({enabled:!s.enabled}, s.enabled ? "Страница выключена" : "Страница включена")}>
            Страница включена
          </Toggle>
          <Toggle on={s.show_qr} onClick={() => save({show_qr:!s.show_qr}, "Сохранено")}>Показывать QR-код</Toggle>
        </div>
        <div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
          Ссылку клиента создаёт кнопка <b>QR</b> на странице «Клиенты» или команда бота <code>/link имя</code>.
          Разметка текста: <code># Заголовок</code>, <code>## Подзаголовок</code>, списки <code>-</code> и <code>1.</code>,
          <code>**жирный**</code>, <code>`код`</code>, <code>[текст](https://…)</code>. HTML не поддерживается.
        </div>
        <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
          {Object.entries(s.placeholders).map(([k, label]) => (
            <button key={k} onClick={() => insert(k)} title={label} style={{padding:"3px 8px",borderRadius:"var(--radius)",fontSize:12,cursor:"pointer",
              fontFamily:"var(--mono)",background:"var(--surface2)",border:"1px solid var(--border)",color:"var(--cyan)"}}>{`{${k}}`}</button>
          ))}
        </div>
        <textarea ref={area} value={tpl} onChange={e => setTpl(e.target.value)} rows={14} spellCheck={false}
          style={{background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",padding:"8px 10px",
            fontSize:14,width:"100%",boxSizing:"border-box",fontFamily:"var(--mono)",resize:"vertical",lineHeight:1.5}}/>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <Btn v="ghost" onClick={showPreview}>Предпросмотр</Btn>
          {s.custom && <Btn v="ghost" onClick={() => save({template:s.default_template}, "Шаблон сброшен")} disabled={busy}>↺ Шаблон по умолчанию</Btn>}
          <Btn v="primary" onClick={() => save({template:tpl}, "Шаблон сохранён")} disabled={busy || !dirty} style={{marginLeft:"auto"}}>
            {busy ? "Сохранение…" : "Сохранить"}
          </Btn>
        </div>
        {preview && (
          <div style={{border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",overflow:"hidden"}}>
            <div style={{display:"flex",alignItems:"center",padding:"6px 10px",fontSize:12,color:"var(--muted)",background:"var(--surface2)"}}>
              <span style={{flex:1}}>Пример для вымышленного клиента</span>
              <button onClick={() => setPreview("")} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer"}}>✕</button>
            </div>
            <iframe title="Предпросмотр страницы пользователя" sandbox="" srcDoc={preview}
              style={{width:"100%",height:520,border:"none",display:"block",background:"#fff"}}/>
          </div>
        )}
      </div>
    </Card>
  );
};
