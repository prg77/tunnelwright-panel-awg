import React, { useState } from "react";
import { api } from "../api";
import { clientUsageStore } from "../stores/clientUsage";
import { thStore } from "../stores/trafficHistory";

// ─── ResetTrafficCard ─────────────────────────────────────────
export const ResetTrafficCard = ({ T, push, setTrafficPts, setClientUsage }) => {
  const [resetting, setResetting] = useState(false);
  const [resetDone, setResetDone] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const doReset = async () => {
    setShowConfirm(false);
    setResetting(true);
    try {
      await api.resetTraffic();
      thStore.clear();
      clientUsageStore.clear();
      setTrafficPts([]);
      setClientUsage({});
      setResetDone(true);
      push({type:"ok", title:"Трафик сброшен", detail:"История обнулена на сервере и во всех браузерах"});
      setTimeout(()=>setResetDone(false), 4000);
    } catch(e) {
      push({type:"err", title:"Трафик не сброшен", detail:e.message});
    } finally { setResetting(false); }
  };
  return (
    <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",overflow:"hidden"}}>
      <div style={{padding:"12px 18px 8px",borderBottom:"1px solid var(--border)"}}>
        <div style={{fontWeight:700,fontSize:14}}>Сброс трафика</div>
        <div style={{fontSize:12,color:"var(--muted)",marginTop:3}}>обнуляет историю графиков и топ-клиентов на сервере и во всех браузерах</div>
      </div>
      <div style={{padding:"12px 18px",display:"flex",alignItems:"center",gap:14}}>
        {showConfirm&&(
          <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.75)",backdropFilter:"blur(4px)",
            zIndex:9999,display:"flex",alignItems:"center",justifyContent:"center"}}
            onClick={()=>setShowConfirm(false)}>
            <div style={{background:"var(--surface)",border:"1px solid color-mix(in srgb,var(--error) 40%,transparent)",borderRadius:"var(--radius-lg)",
              padding:24,maxWidth:380,width:"100%",margin:16}} onClick={e=>e.stopPropagation()}>
              <div style={{fontSize:16,fontWeight:700,marginBottom:8}}>Сброс трафика</div>
              <div style={{fontSize:14,color:"var(--muted)",marginBottom:6,lineHeight:1.6}}>
                Будут удалены:
              </div>
              <div style={{fontSize:14,lineHeight:1.8,marginBottom:16,padding:"10px 14px",
                background:"color-mix(in srgb,var(--error) 6%,transparent)",borderRadius:"var(--radius)",border:"1px solid color-mix(in srgb,var(--error) 20%,transparent)"}}>
                <div>• История графиков трафика (<code style={{fontFamily:"var(--mono)",fontSize:12}}>traffic-history.json</code>)</div>
                <div>• Статистика клиентов — Топ месяца/полугодия/года (<code style={{fontFamily:"var(--mono)",fontSize:12}}>client-usage.json</code>)</div>
                <div>• localStorage в текущем браузере</div>
              </div>
              <div style={{fontSize:12,color:"var(--success)",marginBottom:16}}>
                ✓ Лимиты скорости, группы и настройки клиентов — <b>не затрагиваются</b>
              </div>
              <div style={{display:"flex",gap:10}}>
                <button onClick={doReset} style={{flex:1,padding:"9px 0",borderRadius:"var(--radius)",
                  border:"none",background:"color-mix(in srgb,var(--error) 15%,transparent)",color:"var(--error)",
                  fontSize:14,fontWeight:700,cursor:"pointer"}}>
                  Да, сбросить всё
                </button>
                <button onClick={()=>setShowConfirm(false)} style={{padding:"9px 18px",borderRadius:"var(--radius)",
                  border:"1px solid var(--border)",background:"var(--surface2)",color:"var(--muted)",
                  fontSize:14,cursor:"pointer"}}>
                  Отмена
                </button>
              </div>
            </div>
          </div>
        )}
        <button onClick={()=>setShowConfirm(true)} disabled={resetting}
          style={{padding:"8px 16px",borderRadius:"var(--radius)",border:"1px solid color-mix(in srgb,var(--error) 30%,transparent)",
            background:resetDone?"color-mix(in srgb,var(--success) 10%,transparent)":resetting?"var(--surface2)":"color-mix(in srgb,var(--error) 8%,transparent)",
            color:resetDone?"var(--success)":"var(--error)",fontSize:12,fontWeight:600,
            cursor:resetting?"not-allowed":"pointer",minWidth:160,transition:"all .2s"}}>
          {resetting ? "Сбрасываю..." : resetDone ? "Сброшено" : "Сбросить весь трафик"}
        </button>
        <span style={{fontSize:12,color:"var(--muted)",lineHeight:1.5}}>
          Сбрасывает: графики трафика, топ клиентов (месяц/полгода/год).<br/>
          Лимиты и данные клиентов — <b style={{color:"var(--text)"}}>не затрагиваются</b>.
        </span>
      </div>
    </div>
  );
};
