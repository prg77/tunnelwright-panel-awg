import React, { useState, useEffect } from "react";
import { api } from "../api";
import { useGroups } from "../stores/groups";
import { aColor, fmtGB } from "../utils/format";

const label = {display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8};
const field = {width:"100%",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",
  fontSize:14,padding:"9px 12px",outline:"none",boxSizing:"border-box",display:"block"};

// ─── UserModal — пользователь: имя, группа, срок, заметка, квота; объединение с другими ──
// Срок, включение и квота действуют на все устройства пользователя.
export const UserModal = ({ user, users, onSave, onMerge, onClose }) => {
  const { names: GROUPS, colors: GC } = useGroups();
  const [name,setName]=useState(user.name||"");
  const [note,setNote]=useState(user.note||"");
  const [group,setGroup]=useState(user.group||"Без группы");
  const [exp,setExp]=useState(user.expiresAt?user.expiresAt.slice(0,10):"");
  // Квота трафика: ГБ за календарный месяц на все устройства (пусто — без квоты)
  const [quota,setQuota]=useState(null);       // {limit_bytes, used_bytes, blocked} с сервера
  const [quotaGb,setQuotaGb]=useState("");
  const [err,setErr]=useState("");
  const [mergeId,setMergeId]=useState("");
  useEffect(()=>{ api.quotas().then(q=>{ const x=q[user.id]; setQuota(x||null); setQuotaGb(x?String(+(x.limit_bytes/1073741824).toFixed(2)):""); }).catch(()=>{}); },[user.id]);
  const save=async()=>{
    if(!name.trim()){ setErr("Имя не может быть пустым"); return; }
    const gb=quotaGb.trim()===""?null:Number(quotaGb.replace(",","."));
    if(gb!==null&&(!Number.isFinite(gb)||gb<0)){ setErr("Квота: введите число ГБ или оставьте пустым"); return; }
    const before=quota?+(quota.limit_bytes/1073741824).toFixed(2):null;
    if((gb||null)!==before){ try{ await api.setQuota(user.id,gb); }catch(e){ setErr(e.message); return; } }
    onSave({name:name.trim(),note,group:group!=="Без группы"?group:"",expiresAt:exp?new Date(exp).toISOString():null});
    onClose();
  };
  const others=(users||[]).filter(u=>u.id!==user.id).sort((a,b)=>a.name.localeCompare(b.name,"ru"));
  const createdAt=user.createdAt?new Date(user.createdAt.replace(" ","T")+"Z").toLocaleString("ru",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}):"Неизвестно";
  const daysLeft=exp?Math.ceil((new Date(exp)-Date.now())/86400000):null;
  return(<div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(6px)",zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
    <div className="meta-modal-inner" style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:24,maxWidth:400,width:"100%",animation:"pop .22s ease",maxHeight:"92vh",overflowY:"auto"}} onClick={e=>e.stopPropagation()}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:20}}>
        <div style={{width:36,height:36,borderRadius:"50%",background:aColor(user.name),display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,fontWeight:700,color:"#fff",flexShrink:0}}>{(user.name||"?").charAt(0).toUpperCase()}</div>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:700,fontSize:15}}>{user.name}<span title="ID пользователя — различает одинаковые имена" style={{marginLeft:7,fontSize:12,fontWeight:400,color:"var(--muted)",fontFamily:"var(--mono)"}}>#{user.uid}</span></div>
          <div style={{fontSize:12,color:"var(--muted)"}}>устройств: {user.configs.length} · создан {createdAt}</div>
        </div>
        <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:20}}>✕</button>
      </div>
      <div style={{marginBottom:14}}>
        <label style={label}>Имя</label>
        <input value={name} onChange={e=>{setName(e.target.value);setErr("");}} maxLength={64} style={field}/>
      </div>
      <div style={{marginBottom:14}}>
        <div style={label}>Группа</div>
        <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{GROUPS.map(g=>(<button key={g} onClick={()=>setGroup(g)} style={{padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:12,fontWeight:600,border:`1px solid ${group===g?GC[g]:"var(--border)"}`,background:group===g?`${GC[g]}18`:"var(--surface2)",color:group===g?GC[g]:"var(--muted)"}}>{g}</button>))}</div>
      </div>
      <div style={{marginBottom:14}}>
        <label style={label}>
          Срок доступа {daysLeft!==null&&<span style={{marginLeft:6,color:daysLeft<0?"var(--error)":daysLeft<7?"var(--warning)":"var(--success)",fontWeight:600}}>{daysLeft<0?`⚠ истёк ${Math.abs(daysLeft)}д`:`✓ ещё ${daysLeft}д`}</span>}
        </label>
        <input type="date" value={exp} onChange={e=>setExp(e.target.value)} style={{...field,fontFamily:"var(--mono)"}}/>
        {exp&&<button onClick={()=>setExp("")} style={{marginTop:5,fontSize:12,color:"var(--muted)",background:"none",border:"none",cursor:"pointer",padding:0}}>Убрать срок</button>}
      </div>
      <div style={{marginBottom:14}}>
        <label style={label}>Заметка</label>
        <textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="Мама, гость до мая..." rows={2} style={{...field,resize:"vertical"}}/>
      </div>
      <div style={{marginBottom:14}}>
        <label style={label}>
          Квота трафика, ГБ в месяц {quota&&<span style={{marginLeft:6,color:quota.blocked?"var(--error)":"var(--cyan)",fontWeight:600}}>
            {quota.blocked?"исчерпана":`использовано ${fmtGB(quota.used_bytes)}`}</span>}
        </label>
        <input inputMode="decimal" value={quotaGb} onChange={e=>{setQuotaGb(e.target.value);setErr("");}} placeholder="без квоты" style={{...field,fontFamily:"var(--mono)"}}/>
        <div style={{fontSize:12,color:"var(--muted)",marginTop:5}}>
          На все устройства. 80 % — предупреждение в Telegram, 100 % — пользователь отключается до начала следующего месяца
        </div>
      </div>
      {err&&<div className="alert alert-error" style={{marginBottom:14}}>{err}</div>}
      <div style={{display:"flex",gap:10}}>
        <button onClick={save} style={{flex:1,padding:"10px 0",background:"var(--primary)",border:"none",borderRadius:"var(--radius)",color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer"}}>Сохранить</button>
        <button onClick={onClose} style={{padding:"10px 18px",background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--muted)",fontSize:14,cursor:"pointer"}}>Отмена</button>
      </div>
      {/* Объединение: устройства другого пользователя переходят к этому */}
      {others.length>0&&<div style={{marginTop:18,paddingTop:14,borderTop:"1px solid var(--border)"}}>
        <div style={label}>Объединить с другим пользователем</div>
        <div style={{display:"flex",gap:8}}>
          <select value={mergeId} onChange={e=>setMergeId(e.target.value)} style={{flex:1,minWidth:0}}>
            <option value="">— выберите —</option>
            {others.map(u=><option key={u.id} value={u.id}>{u.name} · #{u.uid} · устройств: {u.configs.length}</option>)}
          </select>
          <button disabled={!mergeId} onClick={()=>{ const o=others.find(u=>String(u.id)===mergeId); if(o){ onMerge(o); onClose(); } }}
            style={{padding:"0 12px",background:"var(--surface2)",border:"1px solid var(--border-medium)",borderRadius:"var(--radius)",color:mergeId?"var(--text)":"var(--disabled)",fontSize:14,cursor:mergeId?"pointer":"default"}}>Объединить</button>
        </div>
        <div style={{fontSize:12,color:"var(--muted)",marginTop:5,lineHeight:1.5}}>
          Устройства выбранного пользователя перейдут к «{user.name}», сам он будет удалён вместе со своей ссылкой и квотой.
          Ключи и конфиги устройств не меняются.
        </div>
      </div>}
    </div>
  </div>);
};
