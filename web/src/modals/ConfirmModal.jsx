import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── ConfirmModal ─────────────────────────────────────────────────
export const ConfirmModal = ({ title, detail, confirmLabel="Удалить", onConfirm, onClose }) => (
  <div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(6px)",
    zIndex:9995,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}
    onClick={onClose}>
    <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",
      padding:28,maxWidth:360,width:"100%",animation:"pop .2s ease"}}
      onClick={e=>e.stopPropagation()}>
      <div style={{fontSize:15,fontWeight:700,marginBottom:8,color:"var(--text)"}}>{title}</div>
      {detail&&<div style={{fontSize:14,color:"var(--muted)",marginBottom:20,lineHeight:1.6}}>{detail}</div>}
      <div style={{display:"flex",gap:8}}>
        <button onClick={()=>{onConfirm();onClose();}}
          style={{flex:1,padding:"10px 0",background:"color-mix(in srgb,var(--error) 15%,transparent)",
            border:"1px solid color-mix(in srgb,var(--error) 35%,transparent)",borderRadius:"var(--radius)",
            color:"var(--error)",fontSize:14,fontWeight:700,cursor:"pointer"}}>
          {confirmLabel}
        </button>
        <button onClick={onClose}
          style={{flex:1,padding:"10px 0",background:"var(--surface2)",
            border:"1px solid var(--border)",borderRadius:"var(--radius)",
            color:"var(--muted)",fontSize:14,cursor:"pointer"}}>
          Отмена
        </button>
      </div>
    </div>
  </div>
);

