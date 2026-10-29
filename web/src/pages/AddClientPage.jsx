import React, { useState, useEffect } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";
import { useGroups } from "../stores/groups";
import { getLastOctet, getPrefix } from "../utils/ip";

export const DEFAULT_LIMIT = { down: 5, up: 5 };


// Пользователь с первым устройством создаётся одним запросом: панель заводит профиль на всех нодах,
// сохраняет группу, заметку и лимит и сама отправляет уведомление в Telegram (если включено).
// Ещё устройства добавляются в списке пользователей (кнопка «+»).
export const AddClientPage = ({ push, setQrClient, setPage, clients, onCreated }) => {
  const { names: GROUPS, colors: GC } = useGroups();
  const [addName,  setAddName]  = useState("");
  const [addDevice,setAddDevice]= useState("");
  const [addGroup, setAddGroup] = useState("Без группы");
  const [addExp,   setAddExp]   = useState("");
  const [addNote,  setAddNote]  = useState("");
  const [limitOn,  setLimitOn]  = useState(false);
  const [limit,    setLimit]    = useState(DEFAULT_LIMIT);
  const [addBusy,  setAddBusy]  = useState(false);
  // Клиент создаётся на всех нодах с одним IP — показываем, на каких
  const [nodeList, setNodeList] = useState(null);
  useEffect(()=>{ api.nodes().then(setNodeList).catch(()=>setNodeList([])); },[]);

  const usedLastOctets = new Set((clients||[]).map(c=>getLastOctet(c.ip)).filter(n=>n!==null));
  const subnetPrefix = (()=>{
    const c=(clients||[]).find(c=>getLastOctet(c.ip)!==null);
    return c ? getPrefix(c.ip) : "10.8.0";
  })();
  // Свободные адреса: .2–.254 (.1 — сервер)
  const freeOctets = Array.from({length:253},(_,i)=>i+2).filter(n=>!usedLastOctets.has(n));
  // Выбор пользователя; пока его нет — первый свободный (список клиентов может догрузиться позже)
  const [pickedOctet, setIpLastOctet] = useState(null);
  const ipLastOctet = pickedOctet!=null && !usedLastOctets.has(pickedOctet) ? pickedOctet : (freeOctets[0]??2);

  const doCreate = async () => {
    const n = addName.trim();
    if(!n){ push({type:"err", title:"Введите имя пользователя"}); return; }
    setAddBusy(true);
    try{
      const created = await api.createClient({
        name: n,
        ...(addDevice.trim() ? {device:addDevice.trim()} : {}),
        ...(freeOctets.length>0 ? {ip:`${subnetPrefix}.${ipLastOctet}`} : {}),
        ...(addExp ? {expiresAt:new Date(addExp).toISOString()} : {}),
        ...(addGroup!=="Без группы" ? {group:addGroup} : {}),
        ...(addNote.trim() ? {note:addNote.trim()} : {}),
        ...(limitOn ? {limit:{down:+limit.down, up:+limit.up}} : {}),
      });
      push({type:"ok", title:`${created.label} создан`, detail:`IP ${created.ip}`
        + (created.nodes.length ? ` · ноды: ${created.nodes.map(x=>x.name).join(", ")}` : " · профили создадутся, когда появится нода")});
      onCreated(created);
      setPage("clients");
      setTimeout(()=>setQrClient(created), 300);
    }catch(e){ push({type:"err", title:"Пользователь не создан", detail:e.message}); }
    finally{ setAddBusy(false); }
  };

  const daysLeft = addExp ? Math.ceil((new Date(addExp)-Date.now())/86400000) : null;

  return (
    <div style={{maxWidth:480,width:"100%"}}>
      <Card>
        <CardH sub="ещё устройства — кнопкой «+» в списке пользователей">Новый пользователь</CardH>
        <div style={{padding:"20px 18px",display:"flex",flexDirection:"column",gap:16}}>

          {/* Имя — обязательное */}
          <div>
            <label style={{display:"block",fontSize:12,color:"var(--muted)",marginBottom:7,
              fontWeight:700}}>
              Имя пользователя <span style={{color:"var(--error)"}}>*</span>
            </label>
            <input autoFocus type="text" value={addName} onChange={e=>setAddName(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&doCreate()}
              placeholder="Мама"
              style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",
                borderRadius:"var(--radius)",color:"var(--text)",fontSize:14,padding:"10px 14px",
                display:"block",boxSizing:"border-box"}}/>
          </div>

          {/* Первое устройство — название необязательное */}
          <div>
            <label style={{display:"block",fontSize:12,color:"var(--muted)",marginBottom:7,fontWeight:700}}>
              Устройство
            </label>
            <input type="text" value={addDevice} onChange={e=>setAddDevice(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&doCreate()} maxLength={64}
              placeholder="iPhone — можно оставить пустым"
              style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",
                borderRadius:"var(--radius)",color:"var(--text)",fontSize:14,padding:"10px 14px",
                display:"block",boxSizing:"border-box"}}/>
          </div>

          {/* Ноды: профиль создаётся на каждой */}
          {nodeList&&<div style={{fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
            {nodeList.length===0
              ? <span style={{color:"var(--warning)"}}>Нод пока нет — устройство получит профили, когда вы добавите ноду (раздел «Ноды»).</span>
              : <>Профиль будет создан на всех нодах:{" "}
                  {nodeList.map((nd,i)=>(<span key={nd.id} title={nd.ok?nd.host:`недоступна — профиль создастся позже`}
                    style={{color:nd.ok?"var(--text)":"var(--warning)"}}>{i>0?", ":""}{nd.ok?"●":"○"} {nd.name}</span>))}</>}
          </div>}

          {/* Группа */}
          <div>
            <div style={{fontSize:12,color:"var(--muted)",fontWeight:700,
              marginBottom:8}}>Группа</div>
            <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
              {GROUPS.map(g=>(
                <button key={g} onClick={()=>setAddGroup(g)} style={{
                  padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",fontSize:12,fontWeight:600,
                  border:`1px solid ${addGroup===g?GC[g]:"var(--border)"}`,
                  background:addGroup===g?`${GC[g]}18`:"var(--surface2)",
                  color:addGroup===g?GC[g]:"var(--muted)"}}>
                  {g}
                </button>
              ))}
            </div>
          </div>

          {/* Срок доступа */}
          <div>
            <label style={{display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,
              marginBottom:8}}>
              Срок доступа
              {daysLeft!==null&&<span style={{marginLeft:6,fontWeight:600,textTransform:"none",
                color:daysLeft<0?"var(--error)":daysLeft<7?"var(--warning)":"var(--success)"}}>
                {daysLeft<0?`⚠ дата в прошлом`:`✓ ${daysLeft} дн.`}
              </span>}
            </label>
            <input type="date" value={addExp} onChange={e=>setAddExp(e.target.value)}
              style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",
                borderRadius:"var(--radius)",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,
                padding:"9px 12px",outline:"none",boxSizing:"border-box",display:"block"}}/>
            {addExp&&<button onClick={()=>setAddExp("")}
              style={{marginTop:5,fontSize:12,color:"var(--muted)",background:"none",border:"none",cursor:"pointer",padding:0}}>
              Убрать срок
            </button>}
          </div>

          {/* Заметка */}
          <div>
            <label style={{display:"block",fontSize:12,color:"var(--muted)",fontWeight:700,
              marginBottom:8}}>Заметка</label>
            <textarea value={addNote} onChange={e=>setAddNote(e.target.value)}
              placeholder="iPhone Мамы, гость до мая…"
              rows={2} style={{width:"100%",background:"var(--bg)",border:"1px solid var(--border)",
                borderRadius:"var(--radius)",color:"var(--text)",fontFamily:"var(--sans)",fontSize:14,
                padding:"9px 12px",outline:"none",resize:"vertical",
                boxSizing:"border-box",display:"block"}}/>
          </div>

          {/* IP адрес — всегда показываем picker */}
          <div>
            <div style={{fontSize:12,color:"var(--muted)",fontWeight:700,marginBottom:8}}>
              IP адрес
            </div>
            <div style={{display:"flex",alignItems:"center",background:"var(--bg)",border:"1px solid var(--border)",borderRadius:"var(--radius)",overflow:"hidden"}}>
              <span style={{padding:"9px 12px",fontSize:14,fontFamily:"var(--mono)",color:"var(--muted)",borderRight:"1px solid var(--border)",flexShrink:0,whiteSpace:"nowrap"}}>{subnetPrefix}.</span>
              <select value={ipLastOctet} onChange={e=>setIpLastOctet(Number(e.target.value))}
                style={{flex:1,background:"var(--bg)",border:"none",color:"var(--text)",fontFamily:"var(--mono)",fontSize:14,padding:"9px 10px",cursor:"pointer",outline:"none"}}>
                {freeOctets.map((n,i)=>(
                  <option key={n} value={n}>{n}/32{i===0?" — следующий свободный":""}</option>
                ))}
              </select>
            </div>
            {freeOctets.length===0&&<div style={{fontSize:12,color:"var(--error)",marginTop:4}}>Все адреса заняты</div>}
          </div>

          {/* Лимит скорости — необязательный */}
          <div>
            <label style={{display:"flex",alignItems:"center",gap:8,fontSize:14,cursor:"pointer"}}>
              <input type="checkbox" checked={limitOn} onChange={e=>setLimitOn(e.target.checked)}/>
              Ограничить скорость
            </label>
            {limitOn&&<div style={{display:"flex",gap:12,marginTop:8}}>
              {[["down","↓ Скачивание"],["up","↑ Отдача"]].map(([k,l])=>(
                <label key={k} className="field" style={{flex:1}}><span style={{fontSize:12,color:"var(--muted)"}}>{l}, Мбит/с</span>
                  <input type="number" min="1" max="10000" value={limit[k]} onChange={e=>setLimit(x=>({...x,[k]:e.target.value}))}/>
                </label>))}
            </div>}
          </div>

          {/* Кнопки */}
          <div style={{display:"flex",gap:10,paddingTop:2}}>
            <Btn v="primary" style={{flex:1,opacity:addBusy?.65:1,cursor:addBusy?"wait":"pointer"}}
              onClick={doCreate}>
              {addBusy?"Создаю…":"Создать"}
            </Btn>
            <Btn v="ghost" onClick={()=>setPage("clients")}>Отмена</Btn>
          </div>

        </div>
      </Card>
    </div>
  );
};
