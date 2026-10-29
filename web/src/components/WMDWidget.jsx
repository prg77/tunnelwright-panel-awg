import React from "react";

// ─── WMDWidget — сводка в боковом меню: клиенты онлайн, RAM, диск ───
// Пороги как у Grafana-гейджей: зелёный → оранжевый → красный.
const level = (pct, warn, crit) => pct == null ? "var(--muted)" : pct > crit ? "var(--error)" : pct > warn ? "var(--warning)" : "var(--success)";

const Row = ({ label, value, extra, pct, color }) => (
  <div style={{padding:"6px 0"}}>
    <div style={{display:"flex",alignItems:"baseline",justifyContent:"space-between",gap:6,fontSize:12}}>
      <span style={{color:"var(--muted)"}}>{label}</span>
      <span style={{fontFamily:"var(--mono)",color}}>
        {value}{extra && <span style={{color:"var(--muted)"}}>{extra}</span>}
      </span>
    </div>
    {pct != null && <div style={{height:4,background:"var(--wmd-bar)",borderRadius:"var(--radius)",marginTop:4,overflow:"hidden"}}>
      <div style={{height:"100%",width:`${Math.min(pct,100)}%`,background:color,transition:"width .7s ease"}}/>
    </div>}
  </div>
);

export const WMDWidget = ({ online, active, stats, fmtBytes, fmtGB }) => {
  const mPct = stats ? Math.round(stats.ram_pct) : null;
  const dPct = stats && !isNaN(stats.disk_pct) ? Math.round(stats.disk_pct) : null;
  return (
    <div style={{margin:"0 16px 8px",padding:"4px 0",borderTop:"1px solid var(--border)"}}>
      <Row label="Онлайн" color={online > 0 ? "var(--success)" : "var(--muted)"}
        value={online} extra={` / ${active}`}/>
      <Row label="RAM" value={mPct != null ? `${mPct}%` : "—"} pct={mPct} color={level(mPct, 70, 85)}
        extra={stats?.ram_used > 0 ? ` · ${fmtBytes(stats.ram_used)}` : null}/>
      <Row label="Диск" value={dPct != null ? `${dPct}%` : "—"} pct={dPct} color={level(dPct, 75, 90)}
        extra={stats?.disk_used > 0 ? ` · ${fmtGB(stats.disk_used)}` : null}/>
    </div>
  );
};
