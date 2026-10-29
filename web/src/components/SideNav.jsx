import React from "react";
import { WMDWidget } from "../components/WMDWidget";
import { APP_VERSION } from "../theme/constants";

// ─── SideNav — боковое меню в стиле Grafana ──────────────────────────
// Объявлен ВНЕ App → React видит стабильный тип → нет unmount/remount при polling.
// collapsed — только иконки (свёрнутое меню на десктопе).
const ic = (children) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;

export const NAV_SECTIONS = [
  { items: [
    {id:"dashboard", label:"Обзор", svg:ic(<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>)},
  ]},
  { title:"VPN", items: [
    {id:"clients", label:"Пользователи", badge:true, svg:ic(<><circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0-3-3.87"/></>)},
    {id:"add",     label:"Новый пользователь", svg:ic(<><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></>)},
    {id:"nodes",   label:"Ноды", svg:ic(<><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><line x1="7" y1="7" x2="7.01" y2="7"/><line x1="7" y1="17" x2="7.01" y2="17"/></>)},
    {id:"lists",   label:"Списки", svg:ic(<><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></>)},
  ]},
  { title:"Администрирование", items: [
    {id:"logs",     label:"Журнал", svg:ic(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></>)},
    {id:"settings", label:"Настройки", svg:ic(<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>)},
  ]},
];
export const NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items);
export const LOGOUT_SVG = ic(<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></>);

const Item = ({ id, label, svg, active, collapsed, onClick, count }) => (
  <button data-id={id} onClick={onClick} title={collapsed ? label : undefined}
    className={`nav-item${active ? " nav-active" : ""}`}
    style={collapsed ? {justifyContent:"center",padding:0} : undefined}>
    <span className="nav-icon">{svg}</span>
    {!collapsed && <span style={{flex:1,textAlign:"left",overflow:"hidden",textOverflow:"ellipsis"}}>{label}</span>}
    {!collapsed && count != null && <span className="nav-count">{count}</span>}
  </button>
);

export const SideNav = React.memo(({ page, setPage, setSideOpen, T, online, active, stats, fmtBytes, fmtGB, doLogout, clientsCount, collapsed }) => (
  <div style={{display:"flex",flexDirection:"column",flex:1,minHeight:0,padding:"8px 0"}}>
    {NAV_SECTIONS.map((s, i) => (
      <div key={i} style={{marginBottom:8}}>
        {s.title && !collapsed && <div className="nav-section">{s.title}</div>}
        {s.title && collapsed && <div style={{height:1,background:"var(--border)",margin:"6px 12px"}}/>}
        {s.items.map(({id,label,svg,badge}) => (
          <Item key={id} id={id} label={label} svg={svg} collapsed={collapsed} active={page===id}
            count={badge ? clientsCount : null}
            onClick={() => { setPage(id); setSideOpen(false); }}/>
        ))}
      </div>
    ))}
    <div style={{marginTop:"auto"}}>
      {!collapsed && <WMDWidget T={T} online={online} active={active} stats={stats} fmtBytes={fmtBytes} fmtGB={fmtGB}/>}
      <Item id="logout" label="Выйти" svg={LOGOUT_SVG} collapsed={collapsed} onClick={doLogout}/>
      {!collapsed && <div style={{padding:"8px 16px 4px",fontSize:12,color:"var(--muted)",display:"flex",justifyContent:"space-between"}}>
        <span>Версия</span><span style={{fontFamily:"var(--mono)"}}>{APP_VERSION}</span>
      </div>}
    </div>
  </div>
));
