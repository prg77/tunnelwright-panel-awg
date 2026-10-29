import React, { useState } from "react";
import { getLastOctet, getPrefix } from "../utils/ip";

const label = {display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8};

// ─── ConfigModal — устройство пользователя: название и IP ─────────
// config — изменение существующего; без него — новое устройство пользователя user.
export const ConfigModal = ({ config, user, allClients, onSave, onClose }) => {
  const editing = !!config;
  const [name,setName]=useState(config?.name||"");
  const [busy,setBusy]=useState(false);
  const used=new Set((allClients||[]).filter(c=>c.id!==config?.id).map(c=>getLastOctet(c.ip)).filter(n=>n!==null));
  const sample=config?.ip||(allClients||[]).find(c=>getLastOctet(c.ip)!==null)?.ip;
  const pfx=sample?getPrefix(sample):"10.8.0";
  const curOct=config?getLastOctet(config.ip):null;
  const free=Array.from({length:253},(_,i)=>i+2).filter(n=>!used.has(n)&&n!==curOct);
  const options=curOct!=null?[curOct,...free]:free;
  const [oct,setOct]=useState(curOct??free[0]??null);
  const save=async()=>{
    setBusy(true);
    const patch={name:name.trim()};
    if(oct!=null&&oct!==curOct) patch.ip=`${pfx}.${oct}`;
    try{ await onSave(patch); onClose(); }
    catch{ /* ошибку уже показало уведомление — окно остаётся открытым */ }
    finally{ setBusy(false); }
  };
  return(<div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(6px)",zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
    <div className="meta-modal-inner" style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:24,maxWidth:380,width:"100%",animation:"pop .22s ease"}} onClick={e=>e.stopPropagation()}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:700,fontSize:15}}>{editing?"Устройство":"Новое устройство"}</div>
          <div style={{fontSize:12,color:"var(--muted)"}}>{editing?config.label:user.name}{editing&&config.uid&&<span style={{fontFamily:"var(--mono)"}}> · #{config.uid}</span>}</div>
        </div>
        <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:20}}>✕</button>
      </div>
      <div style={{marginBottom:14}}>
        <label style={label}>Название устройства</label>
        <input autoFocus value={name} onChange={e=>setName(e.target.value)} maxLength={64} placeholder="iPhone, ноутбук, роутер…"
          onKeyDown={e=>e.key==="Enter"&&!busy&&save()} style={{width:"100%"}}/>
        <div style={{fontSize:12,color:"var(--muted)",marginTop:5}}>
          На нодах и в файлах конфига: «{user?.name||config?.user}{name.trim()?` · ${name.trim()}`:""}»
        </div>
      </div>
      <div style={{marginBottom:18}}>
        <div style={label}>IP адрес</div>
        {options.length===0
          ? <div style={{fontSize:12,color:"var(--error)"}}>Все адреса заняты</div>
          : <div style={{display:"flex",alignItems:"center",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",overflow:"hidden"}}>
            <span style={{padding:"9px 12px",fontSize:14,fontFamily:"var(--mono)",color:"var(--muted)",borderRight:"1px solid var(--border)",flexShrink:0}}>{pfx}.</span>
            <select value={oct??""} onChange={e=>setOct(Number(e.target.value))}
              style={{flex:1,background:"var(--bg)",border:"none",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,padding:"9px 10px",cursor:"pointer"}}>
              {options.map((n,i)=><option key={n} value={n}>{n}{n===curOct?" (текущий)":!editing&&i===0?" — следующий свободный":""}</option>)}
            </select>
          </div>}
        {editing&&oct!==curOct&&<div style={{fontSize:12,color:"var(--warning)",marginTop:5}}>После смены адреса выдайте устройству конфиг заново</div>}
      </div>
      <div style={{display:"flex",gap:10}}>
        <button onClick={save} disabled={busy||options.length===0} style={{flex:1,padding:"10px 0",background:"var(--primary)",border:"none",borderRadius:"var(--radius)",color:"#fff",fontSize:14,fontWeight:700,cursor:busy?"wait":"pointer",opacity:busy?.7:1}}>{editing?"Сохранить":"Создать"}</button>
        <button onClick={onClose} style={{padding:"10px 18px",background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--muted)",fontSize:14,cursor:"pointer"}}>Отмена</button>
      </div>
    </div>
  </div>);
};
