import React from "react";

// ─── Общие элементы интерфейса в стиле Grafana (цвета — theme/tokens.css) ───
// Card — панель: плоский фон, тонкая граница, радиус 4px. CardH — заголовок панели.
export const Card  = ({children,style}) => <div className="panel" style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",overflow:"hidden",...style}}>{children}</div>;
export const CardH = ({children,right,sub}) => (
  <div style={{padding:"8px 16px",minHeight:40,borderBottom:"1px solid var(--border)",display:"flex",alignItems:sub?"flex-start":"center",gap:8}}>
    <div style={{flex:1,minWidth:0}}>
      <div style={{fontSize:14,fontWeight:500,color:"var(--text)",display:"flex",alignItems:"center",gap:8,flexWrap:"wrap",lineHeight:"24px"}}>{children}</div>
      {sub&&<div style={{fontSize:12,color:"var(--muted)",marginTop:0,lineHeight:1.5}}>{sub}</div>}
    </div>
    {right&&<div style={{flexShrink:0}}>{right}</div>}
  </div>
);

// Кнопка: primary — основное действие, ghost — вторичная, danger/amber — контурные
export const Btn = ({onClick,v="ghost",children,disabled,style,title,type="button"}) => (
  <button type={type} onClick={onClick} disabled={disabled} title={title}
    className={`btn btn-${v}`}
    style={{
      display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,
      padding:v==="icon"?0:"0 16px",height:32,width:v==="icon"?32:undefined,borderRadius:"var(--radius)",
      cursor:disabled?"not-allowed":"pointer",
      fontFamily:"var(--sans)",fontSize:14,fontWeight:500,lineHeight:1,
      whiteSpace:"nowrap",flexShrink:0,userSelect:"none",
      opacity:disabled?.6:1,
      ...style}}>
    {children}
  </button>
);
