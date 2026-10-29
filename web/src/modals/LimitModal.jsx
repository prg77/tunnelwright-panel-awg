import React, { useState, useEffect, useRef, useCallback } from "react";

export const LimitModal = ({ data, onSave, onRemove, onClose }) => {
  const [down, setDown] = useState(data.down ?? 5);
  const [up,   setUp]   = useState(data.up   ?? 5);
  const hasLimit = data.hasLimit;  // есть ли лимит сейчас
  const presets  = [1, 2, 5, 10, 25, 50, 100];

  const SliderRow = ({ label, val, set }) => (
    <div style={{marginBottom:20}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
        <span style={{fontSize:14,color:"var(--muted)",fontWeight:600}}>{label}</span>
        <span style={{color:"var(--cyan)",fontFamily:"var(--mono)",fontSize:16,fontWeight:700,minWidth:70,textAlign:"right"}}>
          {val} <span style={{fontSize:12,color:"var(--muted)",fontWeight:400}}>Мбит/с</span>
        </span>
      </div>
      {/* Slider с визуальным track */}
      <div style={{position:"relative",marginBottom:10}}>
        <input type="range" min="1" max="500" step="1" value={val}
          onChange={e=>set(+e.target.value)}
          style={{width:"100%",accentColor:"var(--cyan)",cursor:"pointer",display:"block",height:4}}/>
        {/* Подписи min/max */}
        <div style={{display:"flex",justifyContent:"space-between",marginTop:4,fontSize:11,color:"var(--muted)",fontFamily:"var(--mono)"}}>
          <span>1</span><span>500 Мбит</span>
        </div>
      </div>
      {/* Пресеты */}
      <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
        {presets.map(p=>(
          <button key={p} onClick={()=>set(p)}
            style={{flex:"1 1 auto",padding:"5px 4px",borderRadius:"var(--radius)",
              border:`1px solid ${val===p?"var(--cyan)":"var(--border)"}`,
              background:val===p?"var(--cyan)":"var(--surface2)",
              color:val===p?"#fff":"var(--muted)",
              fontSize:12,fontFamily:"var(--mono)",cursor:"pointer",fontWeight:700,
              transition:"all .12s"}}>
            {p}M
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(6px)",
      zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}
      onClick={onClose}>
      <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",
        padding:26,maxWidth:380,width:"100%",animation:"pop .22s ease",maxHeight:"92vh",overflowY:"auto"}}
        onClick={e=>e.stopPropagation()}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
          <span style={{fontSize:20}}>⚡</span>
          <div style={{flex:1}}>
            <div style={{fontSize:15,fontWeight:700}}>Лимит скорости</div>
            <div style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)",marginTop:2}}>{data.ip}</div>
          </div>
          {/* Статус текущего лимита */}
          <div style={{textAlign:"right"}}>
            {hasLimit
              ? <span style={{fontSize:12,color:"var(--amber)",fontFamily:"var(--mono)",fontWeight:700}}>
                  ↓{data.down}M ↑{data.up}M<br/>
                  <span style={{fontSize:11,color:"var(--muted)",fontWeight:400}}>текущий</span>
                </span>
              : <span style={{fontSize:12,color:"var(--muted)"}}>нет лимита</span>}
          </div>
          <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:18,padding:"0 2px"}}>✕</button>
        </div>

        <div style={{height:1,background:"var(--border)",margin:"14px 0"}}/>

        <SliderRow label="↓ К клиенту (download)" val={down} set={setDown}/>
        <SliderRow label="↑ От клиента (upload)"  val={up}   set={setUp}/>

        {/* Инфо */}
        <div style={{background:"rgba(245,158,11,.05)",border:"1px solid rgba(245,158,11,.18)",
          borderRadius:"var(--radius)",padding:"9px 12px",fontSize:12,color:"var(--muted)",marginBottom:18,lineHeight:1.8}}>
          Применяется через <b style={{color:"var(--amber)"}}>tc qdisc</b> — мгновенно после сохранения.<br/>
          Восстанавливается автоматически каждые 5 мин (переживает рестарт).<br/>
          ✕ «Снять» — убирает все ограничения для этого клиента.
        </div>

        {/* Actions */}
        <div style={{display:"flex",gap:8}}>
          <button onClick={()=>{onSave(data.ip,down,up);onClose();}}
            style={{flex:1,padding:"11px 0",background:"var(--primary)",border:"none",borderRadius:"var(--radius)",
              color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer"}}>
            Применить
          </button>
          <button
            onClick={()=>{onRemove(data.ip);onClose();}}
            disabled={!hasLimit}
            title={hasLimit ? "Убрать ограничение скорости" : "Лимит не установлен"}
            style={{padding:"11px 16px",
              background: hasLimit?"color-mix(in srgb,var(--error) 10%,transparent)":"var(--surface2)",
              border: hasLimit?"1px solid color-mix(in srgb,var(--error) 25%,transparent)":"1px solid var(--border)",
              borderRadius:"var(--radius)",
              color: hasLimit?"var(--error)":"var(--muted)",
              fontSize:14,cursor:hasLimit?"pointer":"not-allowed",
              fontWeight:600,opacity:hasLimit?1:0.45,transition:"all .15s"}}>
            Снять
          </button>
        </div>
      </div>
    </div>
  );
};

