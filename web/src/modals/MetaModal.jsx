import React, { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";
import { useGroups } from "../stores/groups";
import { aColor, fmtGB } from "../utils/format";
import { getLastOctet, getPrefix } from "../utils/ip";

// ─── MetaModal ────────────────────────────────────────────────────
export const MetaModal = ({ client, meta, allClients, onSave, onClose }) => {
  const { names: GROUPS, colors: GC } = useGroups();
  const [note,setNote]=useState(meta.note||"");
  const [group,setGroup]=useState(meta.group||"Без группы");
  const [exp,setExp]=useState(meta.expiresAt?meta.expiresAt.slice(0,10):"");
  const [ipOct,setIpOct]=useState(()=>getLastOctet(client.ip)??2);
  // Квота трафика: ГБ за календарный месяц (пусто — без квоты)
  const [quota,setQuota]=useState(null);       // {limit_bytes, used_bytes, blocked} с сервера
  const [quotaGb,setQuotaGb]=useState("");
  const [quotaErr,setQuotaErr]=useState("");
  useEffect(()=>{ api.quotas().then(q=>{ const x=q[client.id]; setQuota(x||null); setQuotaGb(x?String(+(x.limit_bytes/1073741824).toFixed(2)):""); }).catch(()=>{}); },[client.id]);
  const save=async()=>{
    const gb=quotaGb.trim()===""?null:Number(quotaGb.replace(",","."));
    if(gb!==null&&(!Number.isFinite(gb)||gb<0)){ setQuotaErr("Введите число ГБ или оставьте пустым"); return; }
    const before=quota?+(quota.limit_bytes/1073741824).toFixed(2):null;
    if((gb||null)!==before){ try{ await api.setQuota(client.id,gb); }catch(e){ setQuotaErr(e.message); return; } }
    onSave({note,group,expiresAt:exp||null,ipLastOctet:ipOct});
    onClose();
  };
  const createdAt=meta.createdAt?new Date(meta.createdAt).toLocaleString("ru",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}):"Неизвестно";
  const daysLeft=exp?Math.ceil((new Date(exp)-Date.now())/86400000):null;
  return(<div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(6px)",zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
    <div className="limit-modal-inner" style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:24,maxWidth:380,width:"100%",animation:"pop .22s ease",maxHeight:"92vh",overflowY:"auto"}} onClick={e=>e.stopPropagation()}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <div style={{width:36,height:36,borderRadius:"50%",background:aColor(client.name),display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,fontWeight:700,color:"#fff",flexShrink:0}}>{(client.name||"?").charAt(0).toUpperCase()}</div>
        <div style={{flex:1}}><div style={{fontWeight:700,fontSize:15}}>{client.name}{client.uid&&<span title="ID клиента — различает одинаковые имена" style={{marginLeft:7,fontSize:12,fontWeight:400,color:"var(--muted)",fontFamily:"var(--mono)"}}>#{client.uid}</span>}</div><div style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>{(client.ip||"").replace("/32","")}</div></div>
        <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:20}}>✕</button>
      </div>
      <div style={{display:"flex",gap:8,padding:"8px 12px",background:"var(--border)",border:"1px solid var(--border)",borderRadius:"var(--radius)",marginBottom:16}}>
        <div><div style={{fontSize:11,color:"var(--muted)"}}>Создан</div><div style={{fontSize:14,fontFamily:"var(--mono)"}}>{createdAt}</div></div>
      </div>
      <div style={{marginBottom:14}}>
        <div style={{fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>Группа</div>
        <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{GROUPS.map(g=>(<button key={g} onClick={()=>setGroup(g)} style={{padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:12,fontWeight:600,border:`1px solid ${group===g?GC[g]:"var(--border)"}`,background:group===g?`${GC[g]}18`:"var(--surface2)",color:group===g?GC[g]:"var(--muted)"}}>{g}</button>))}</div>
      </div>
      <div style={{marginBottom:14}}>
        <label style={{display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>
          Срок доступа {daysLeft!==null&&<span style={{marginLeft:6,color:daysLeft<0?"var(--error)":daysLeft<7?"var(--warning)":"var(--success)",fontWeight:600}}>{daysLeft<0?`⚠ истёк ${Math.abs(daysLeft)}д`:`✓ ещё ${daysLeft}д`}</span>}
        </label>
        <input type="date" value={exp} onChange={e=>setExp(e.target.value)} style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,padding:"9px 12px",outline:"none",boxSizing:"border-box",display:"block"}}/>
        {exp&&<button onClick={()=>setExp("")} style={{marginTop:5,fontSize:12,color:"var(--muted)",background:"none",border:"none",cursor:"pointer",padding:0}}>Убрать срок</button>}
      </div>
      <div style={{marginBottom:18}}>
        <label style={{display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>Заметка</label>
        <textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="iPhone Мамы, гость до мая..." rows={2} style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",fontFamily:"var(--sans)",fontSize:14,padding:"9px 12px",outline:"none",resize:"vertical",boxSizing:"border-box",display:"block"}}/>
      </div>
      <div style={{marginBottom:14}}>
        <label style={{display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>
          Квота трафика, ГБ в месяц {quota&&<span style={{marginLeft:6,color:quota.blocked?"var(--error)":"var(--cyan)",fontWeight:600,textTransform:"none"}}>
            {quota.blocked?"исчерпана":`использовано ${fmtGB(quota.used_bytes)}`}</span>}
        </label>
        <input inputMode="decimal" value={quotaGb} onChange={e=>{setQuotaGb(e.target.value);setQuotaErr("");}} placeholder="без квоты"
          style={{width:"100%",background:"var(--bg)",border:`1px solid ${quotaErr?"var(--error)":"var(--border)"}`,borderRadius:"var(--radius)",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,padding:"9px 12px",outline:"none",boxSizing:"border-box"}}/>
        <div style={{fontSize:12,color:quotaErr?"var(--error)":"var(--muted)",marginTop:5}}>
          {quotaErr||"80 % — предупреждение в Telegram, 100 % — клиент отключается до начала следующего месяца"}
        </div>
      </div>
      {/* IP picker в редакторе */}
      {(()=>{
        // Build used set from all OTHER clients (exclude current)
        const allUsed = new Set(
          (allClients||[]).filter(c=>c.id!==client.id)
            .map(c=>getLastOctet(c.ip)).filter(n=>n!==null)
        );
        const pfx = getPrefix(client.ip);
        const curOct = getLastOctet(client.ip) ?? 2;
        // curOct first (labelled "текущий"), then all free octets 2..254 excl. .1
        const freeOcts=[curOct,...Array.from({length:253},(_,i)=>i+2).filter(n=>n!==curOct&&n!==1&&!allUsed.has(n))];
        const [oct,setOct]=[ipOct,setIpOct];
        return(<div style={{marginBottom:14}}>
          <div style={{fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>IP адрес</div>
          <div style={{display:"flex",alignItems:"center",gap:0,background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",overflow:"hidden"}}>
            <span style={{padding:"9px 12px",fontSize:14,fontFamily:"var(--mono)",color:"var(--muted)",borderRight:"1px solid var(--border)",flexShrink:0}}>{pfx}.</span>
            <select value={oct} onChange={e=>setOct(Number(e.target.value))}
              style={{flex:1,background:"var(--bg)",border:"none",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,padding:"9px 10px",cursor:"pointer"}}>
              {freeOcts.map(n=><option key={n} value={n}>{n}{n===curOct?" (текущий)":""}</option>)}
            </select>
          </div>
        </div>);
      })()}
      <div style={{display:"flex",gap:10}}>
        <button onClick={save} style={{flex:1,padding:"10px 0",background:"var(--primary)",border:"none",borderRadius:"var(--radius)",color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer"}}>Сохранить</button>
        <button onClick={onClose} style={{padding:"10px 18px",background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--muted)",fontSize:14,cursor:"pointer"}}>Отмена</button>
      </div>
    </div>
  </div>);
};

