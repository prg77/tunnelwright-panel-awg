import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── Notify ───────────────────────────────────────────────────────
export const TOAST_DURATION = 4200;

export const Toast = ({ note, onDismiss }) => {
  const cfg = {
    ok:   { icon:"✓", accent:"var(--cyan)",  label:"Готово"    },
    err:  { icon:"✕", accent:"var(--error)",      label:"Ошибка"    },
    warn: { icon:"⚠", accent:"var(--amber)", label:"Внимание"  },
    info: { icon:"ℹ", accent:"var(--muted)", label:"Информация" },
  }[note.type] || { icon:"ℹ", accent:"var(--muted)", label:"" };

  return (
    <div
      onClick={onDismiss}
      style={{
        position:"relative", overflow:"hidden",
        background:"var(--surface)",
        border:`1px solid ${cfg.accent}30`,
        borderLeft:`3px solid ${cfg.accent}`,
        borderRadius:"var(--radius-lg)",
        padding:"11px 14px 14px",
        fontSize:14, cursor:"pointer",
        boxShadow:`0 8px 32px rgba(0,0,0,.55), 0 0 0 1px var(--border)`,
        animation:"toastIn .22s cubic-bezier(.34,1.56,.64,1)",
        minWidth:260, maxWidth:340,
        pointerEvents:"all",
        backdropFilter:"blur(8px)",
      }}>
      {/* Header */}
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:note.detail?6:0}}>
        <span style={{
          width:18,height:18,borderRadius:"50%",
          background:`${cfg.accent}18`,
          border:`1px solid ${cfg.accent}40`,
          display:"flex",alignItems:"center",justifyContent:"center",
          fontSize:11,color:cfg.accent,fontWeight:700,flexShrink:0
        }}>{cfg.icon}</span>
        <span style={{fontWeight:600,fontSize:14,color:"var(--text)",flex:1,lineHeight:1.3}}>
          {note.title || cfg.label}
        </span>
        <span style={{fontSize:12,color:"var(--muted)",flexShrink:0}}>✕</span>
      </div>
      {/* Detail */}
      {note.detail && (
        <div style={{
          fontSize:12,color:"var(--muted)",lineHeight:1.5,
          paddingLeft:26,fontFamily:"var(--mono)"
        }}>
          {note.detail}
        </div>
      )}
      {/* Progress bar */}
      <div style={{
        position:"absolute",bottom:0,left:0,height:2,
        background:`${cfg.accent}50`,
        animation:`toastBar ${TOAST_DURATION}ms linear forwards`,
      }}/>
    </div>
  );
};

// ToastStack — вынесен ВНЕ useNotify как стабильный компонент
// Если объявить внутри хука, React создаёт новый тип компонента на каждый рендер
// → unmount/remount → анимация toastIn проигрывается повторно (мигание)
export const ToastStack = ({ notes, onDismiss }) => (
  <div style={{
    position:"fixed", bottom:20, right:20, zIndex:9999,
    display:"flex", flexDirection:"column", gap:8,
    pointerEvents:"none",
  }}>
    <style>{`
      @keyframes toastIn {
        from { opacity:0; transform:translateX(16px) scale(.97); }
        to   { opacity:1; transform:none; }
      }
      @keyframes toastBar {
        from { width:100%; }
        to   { width:0%; }
      }
    `}</style>
    {notes.map(n => <Toast key={n.id} note={n} onDismiss={() => onDismiss(n.id)}/>)}
  </div>
);

export const useNotify = () => {
  const [notes, setNotes] = useState([]);

  const push = useCallback((msgOrObj, type="info") => {
    const id = Date.now() + Math.random();
    const note = typeof msgOrObj === "object"
      ? { id, type: msgOrObj.type || type, title: msgOrObj.title, detail: msgOrObj.detail }
      : { id, type, title: msgOrObj };
    setNotes(n => [...n.slice(-4), note]); // максимум 5 тостов
    setTimeout(() => setNotes(n => n.filter(x => x.id !== id)), TOAST_DURATION);
  }, []);

  const dismiss = useCallback((id) => {
    setNotes(n => n.filter(x => x.id !== id));
  }, []);

  // Stack — стабильная обёртка: передаёт notes и dismiss в ToastStack
  // сама не пересоздаётся как тип, потому что ToastStack объявлен снаружи
  const Stack = useCallback(() => (
    <ToastStack notes={notes} onDismiss={dismiss}/>
  ), [notes, dismiss]);

  return { push, Stack };
};
