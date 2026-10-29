import React, { useState, useEffect, useRef, useCallback } from "react";
import { fmtBytes } from "../utils/format";

// ─── TrafficChart — unified single chart with combined TX+RX ───────
export const TrafficChart = ({ points, period, txSpd, rxSpd, rxColor, txColor }) => {
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);
  // Filter: "both" | "tx" | "rx"
  const [filter, setFilter] = useState("both");
  const showTx = filter !== "rx";
  const showRx = filter !== "tx";

  const now = Date.now();
  const periodMs = {"1h":3600000,"24h":86400000,"7d":604800000,"30d":2592000000}[period]||3600000;
  const windowStart = now - periodMs;
  const pts = (points||[]).filter(p => p.ts >= windowStart);

  // bytes/sec → readable speed
  const fmtSpd = (bps) => {
    if(!bps||isNaN(bps)) return "0 бит/с";
    const b = bps*8;
    if(b>=1e9) return (b/1e9).toFixed(2)+" Гбит/с";
    if(b>=1e6) return (b/1e6).toFixed(2)+" Мбит/с";
    if(b>=1e3) return (b/1e3).toFixed(1)+" Кбит/с";
    return Math.round(b)+" бит/с";
  };
  // Short label for Y axis (no unit words, just number+unit)
  const fmtSpdShort = (bps) => {
    if(!bps||isNaN(bps)) return "0";
    const b = bps*8;
    if(b>=1e9) return (b/1e9).toFixed(1)+"G";
    if(b>=1e6) return (b/1e6).toFixed(1)+"M";
    if(b>=1e3) return (b/1e3).toFixed(0)+"K";
    return Math.round(b)+"";
  };
  const fmtBytes = (n) => {
    if(!n||isNaN(n)) return "0 B";
    if(n>=1e12) return (n/1e12).toFixed(2)+" ТБ";
    if(n>=1e9) return (n/1e9).toFixed(2)+" ГБ";
    if(n>=1e6) return (n/1e6).toFixed(1)+" МБ";
    if(n>=1e3) return (n/1e3).toFixed(1)+" КБ";
    return Math.round(n)+" Б";
  };
  const fmtTime = (ts) => {
    const d = new Date(ts);
    if(period==="1h"||period==="24h") return d.toLocaleTimeString("ru",{hour:"2-digit",minute:"2-digit"});
    return d.toLocaleDateString("ru",{day:"2-digit",month:"2-digit"});
  };

  // Derive speed series from cumulative bytes
  const series = [];
  for(let i=1;i<pts.length;i++){
    const dt = (pts[i].ts - pts[i-1].ts)/1000;
    if(dt<=0||dt>600) continue;
    series.push({
      ts: pts[i].ts,
      tx: Math.max(0,(pts[i].tx - pts[i-1].tx)/dt), // bytes/sec download
      rx: Math.max(0,(pts[i].rx - pts[i-1].rx)/dt), // bytes/sec upload
    });
  }

  const noData = series.length < 2;
  const peakTx = series.reduce((m,p)=>Math.max(m,p.tx),0);
  const peakRx = series.reduce((m,p)=>Math.max(m,p.rx),0);
  const maxV   = Math.max(peakTx, peakRx, 1);
  const totalTx = pts.length>1 ? Math.max(0,(pts[pts.length-1].tx||0)-(pts[0].tx||0)) : 0;
  const totalRx = pts.length>1 ? Math.max(0,(pts[pts.length-1].rx||0)-(pts[0].rx||0)) : 0;

  // SVG dimensions
  const W=900, H=160, PL=72, PR=24, PT=14, PB=30;
  const cW=W-PL-PR, cH=H-PT-PB;

  const toX = (ts) => PL + ((ts-windowStart)/periodMs)*cW;
  const toY = (v)  => PT + cH - (v/maxV)*cH;

  // Build SVG path
  const path = (key) => {
    const pts2 = series.filter(p=>p.ts>=windowStart);
    if(pts2.length<2) return "";
    return pts2.map((p,i)=>`${i===0?"M":"L"}${toX(p.ts).toFixed(1)},${toY(p[key]).toFixed(1)}`).join(" ");
  };

  // Time axis labels
  const tickCount = period==="1h"?6:period==="24h"?8:7;
  const ticks = Array.from({length:tickCount+1},(_,i)=>windowStart+(periodMs/tickCount)*i);

  // Y-axis labels
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map(f=>({v:maxV*f, y:PT+cH*(1-f)}));

  const hoverPt = hover && series.find(p=>Math.abs(toX(p.ts)-hover.x)<(cW/series.length)*2+4);

  return (
    <div style={{width:"100%"}}>
      {/* ── Stats row — ↓/↑ кликабельны для фильтрации ── */}
      <div className="traffic-stats-row" style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:1,
        borderBottom:"1px solid var(--border)",background:"var(--surface2)"}}>

        {/* ↓ Скачивание — кликабельный фильтр */}
        {(()=>{
          const active = showTx;
          const solo   = filter === "tx";
          return (
            <div onClick={()=>setFilter(f=>f==="tx"?"both":"tx")}
              style={{padding:"12px 16px",cursor:"pointer",transition:"all .15s",
                background: solo ? `${rxColor}12` : active ? "transparent" : "var(--surface2)",
                opacity: active ? 1 : 0.4,
                borderBottom: solo ? `2px solid ${rxColor}` : "2px solid transparent",
                userSelect:"none"}}>
              <div className="traffic-stat-label" style={{fontSize:12,color:rxColor,marginBottom:4,display:"flex",alignItems:"center",gap:5,fontWeight:600}}>
                <span style={{width:8,height:8,borderRadius:"50%",background:rxColor,
                  boxShadow:active?`0 0 6px ${rxColor}80`:"none"}}/>
                ↓ Скачивание
                {solo&&<span style={{marginLeft:"auto",fontSize:11,opacity:.7,fontStyle:"italic"}}>только</span>}
              </div>
              <div className="traffic-stat-value" style={{fontSize:18,fontWeight:700,fontFamily:"var(--mono)",color:rxColor,lineHeight:1,marginBottom:3}}>
                {fmtSpd(txSpd*1024)}
              </div>
              <div className="traffic-stat-sub" style={{fontSize:12,color:"var(--muted)",opacity:.7}}>Пик {fmtSpd(peakTx)} · Всего {fmtBytes(totalTx)}</div>
            </div>
          );
        })()}

        {/* ↑ Отдача — кликабельный фильтр */}
        {(()=>{
          const active = showRx;
          const solo   = filter === "rx";
          return (
            <div onClick={()=>setFilter(f=>f==="rx"?"both":"rx")}
              style={{padding:"12px 16px",cursor:"pointer",transition:"all .15s",
                background: solo ? `${txColor}12` : active ? "transparent" : "var(--surface2)",
                opacity: active ? 1 : 0.4,
                borderBottom: solo ? `2px solid ${txColor}` : "2px solid transparent",
                userSelect:"none"}}>
              <div className="traffic-stat-label" style={{fontSize:12,color:txColor,marginBottom:4,display:"flex",alignItems:"center",gap:5,fontWeight:600}}>
                <span style={{width:8,height:8,borderRadius:"50%",background:txColor,
                  boxShadow:active?`0 0 6px ${txColor}80`:"none"}}/>
                ↑ Отдача
                {solo&&<span style={{marginLeft:"auto",fontSize:11,opacity:.7,fontStyle:"italic"}}>только</span>}
              </div>
              <div className="traffic-stat-value" style={{fontSize:18,fontWeight:700,fontFamily:"var(--mono)",color:txColor,lineHeight:1,marginBottom:3}}>
                {fmtSpd(rxSpd*1024)}
              </div>
              <div className="traffic-stat-sub" style={{fontSize:12,color:"var(--muted)",opacity:.7}}>Пик {fmtSpd(peakRx)} · Всего {fmtBytes(totalRx)}</div>
            </div>
          );
        })()}

        {/* Суммарно */}
        <div style={{padding:"12px 16px"}}>
          <div style={{fontSize:12,color:"var(--muted)",marginBottom:4}}>Суммарно</div>
          <div style={{fontSize:18,fontWeight:700,fontFamily:"var(--mono)",color:"var(--text)",lineHeight:1,marginBottom:3}}>
            {fmtSpd((txSpd+rxSpd)*1024)}
          </div>
          <div style={{fontSize:12,color:"var(--muted)",opacity:.7}}>↓+↑ прямо сейчас</div>
        </div>

        {/* Период */}
        <div style={{padding:"12px 16px"}}>
          <div style={{fontSize:12,color:"var(--muted)",marginBottom:4}}>Данных</div>
          <div style={{fontSize:18,fontWeight:700,fontFamily:"var(--mono)",color:"var(--muted)",lineHeight:1,marginBottom:3}}>
            {series.length}
          </div>
          <div style={{fontSize:12,color:"var(--muted)",opacity:.7}}>
            точек за {period==="1h"?"1 час":period==="24h"?"24 часа":period==="7d"?"7 дней":"30 дней"}
            {filter!=="both"&&<span style={{color:filter==="tx"?rxColor:txColor}}> · фильтр</span>}
          </div>
        </div>
      </div>

      {/* ── Chart ── */}
      {noData
        ? <div style={{height:H+PB,display:"flex",flexDirection:"column",alignItems:"center",
            justifyContent:"center",color:"var(--muted)",fontSize:14,gap:6,opacity:.6}}>
            <div>Данные накапливаются…</div>
            <div style={{fontSize:12}}>График появится через несколько минут</div>
          </div>
        : <div style={{position:"relative",userSelect:"none",overflow:"hidden"}}
            onMouseLeave={()=>setHover(null)}
            onMouseMove={e=>{
              const r=e.currentTarget.getBoundingClientRect();
              const svg=svgRef.current;
              if(!svg)return;
              const svgW=svg.clientWidth||W;
              const x=PL+(e.clientX-r.left)/svgW*cW;
              setHover({x});
            }}>
            <svg ref={svgRef} viewBox={`0 0 ${W} ${H+PB}`} width="100%"
              style={{display:"block",overflow:"hidden",maxWidth:"100%"}}>
              <defs>
                <linearGradient id="gradTx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={rxColor} stopOpacity=".35"/>
                  <stop offset="100%" stopColor={rxColor} stopOpacity=".02"/>
                </linearGradient>
                <linearGradient id="gradRx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={txColor} stopOpacity=".25"/>
                  <stop offset="100%" stopColor={txColor} stopOpacity=".02"/>
                </linearGradient>
              </defs>

              {/* Grid lines */}
              {yLabels.map(({y},i)=>(
                <line key={i} x1={PL} y1={y} x2={PL+cW} y2={y}
                  stroke="var(--border)" strokeWidth="1" strokeOpacity=".7"/>
              ))}
              {ticks.map((ts,i)=>(
                <line key={i} x1={toX(ts)} y1={PT} x2={toX(ts)} y2={PT+cH}
                  stroke="var(--border)" strokeWidth="1" strokeOpacity=".5"/>
              ))}

              {/* Y-axis labels */}
              {yLabels.filter((_,i)=>i>0).map(({v,y},i)=>(
                <text key={i} x={PL-8} y={y+4} textAnchor="end" fontSize="10"
                  fill="var(--muted)" fontFamily="Inter,system-ui,sans-serif" fontWeight="500">
                  {fmtSpdShort(v)}
                </text>
              ))}

              {/* X-axis labels */}
              {ticks.map((ts,i)=>(
                <text key={i} x={toX(ts)} y={PT+cH+18} textAnchor="middle" fontSize="10"
                  fill="var(--muted)" fontFamily="Inter,system-ui,sans-serif" fontWeight="500">
                  {fmtTime(ts)}
                </text>
              ))}

              {/* TX fill + line — ↓ Скачивание */}
              {showTx&&<path
                d={path("tx")+" L"+((toX(series[series.length-1]?.ts||now)).toFixed(1))+","+(PT+cH)+" L"+PL+","+(PT+cH)+" Z"}
                fill="url(#gradTx)" stroke="none"/>}
              {showTx&&<path d={path("tx")} fill="none" stroke={rxColor}
                strokeWidth={filter==="tx"?2.2:1.8} strokeLinejoin="round" strokeLinecap="round"/>}

              {/* RX fill + line — ↑ Отдача */}
              {showRx&&<path
                d={path("rx")+" L"+((toX(series[series.length-1]?.ts||now)).toFixed(1))+","+(PT+cH)+" L"+PL+","+(PT+cH)+" Z"}
                fill="url(#gradRx)" stroke="none"/>}
              {showRx&&<path d={path("rx")} fill="none" stroke={txColor}
                strokeWidth={filter==="rx"?2.2:1.5} strokeLinejoin="round" strokeLinecap="round"
                opacity={filter==="both"?.85:1}/>}

              {/* Hover line + tooltip */}
              {hover && hoverPt && (() => {
                const x=toX(hoverPt.ts);
                const yTx=toY(hoverPt.tx);
                const yRx=toY(hoverPt.rx);
                return (<>
                  <line x1={x} y1={PT} x2={x} y2={PT+cH}
                    stroke="var(--muted)" strokeWidth="1" strokeDasharray="3,3" strokeOpacity=".4"/>
                  {showTx&&<circle cx={x} cy={yTx} r="3.5" fill={rxColor} stroke="var(--surface)" strokeWidth="1.5"/>}
                  {showRx&&<circle cx={x} cy={yRx} r="3" fill={txColor} stroke="var(--surface)" strokeWidth="1.5"/>}
                  {/* Tooltip */}
                  {(()=>{
                    const tx=x>W*0.65?x-140:x+8;
                    return (
                      <g>
                        <rect x={tx} y={PT+2} width={132} height={58} rx="5"
                          fill="var(--surface)" stroke="var(--border)" strokeWidth="1"/>
                        <text x={tx+8} y={PT+17} fontSize="10" fill="var(--muted)"
                          fontFamily="Inter,system-ui,sans-serif">{fmtTime(hoverPt.ts)}</text>
                        {showTx&&<><circle cx={tx+10} cy={PT+30} r="3" fill={rxColor}/>
                        <text x={tx+17} y={PT+34} fontSize="10" fill={rxColor}
                          fontFamily="var(--mono)" fontWeight="600">↓ {fmtSpd(hoverPt.tx)}</text></>}
                        {showRx&&<><circle cx={tx+10} cy={showTx?PT+46:PT+30} r="3" fill={txColor}/>
                        <text x={tx+17} y={showTx?PT+50:PT+34} fontSize="10" fill={txColor}
                          fontFamily="var(--mono)" fontWeight="600">↑ {fmtSpd(hoverPt.rx)}</text></>}
                      </g>
                    );
                  })()}
                </>);
              })()}
            </svg>

            {/* Legend — click items to toggle filter */}
            <div className="traffic-legend" style={{display:"flex",gap:6,padding:"8px 16px 12px",fontSize:12,
              alignItems:"center",flexWrap:"wrap"}}>
              {/* ↓ Скачивание toggle */}
              <span onClick={()=>setFilter(f=>f==="tx"?"both":"tx")}
                style={{display:"inline-flex",alignItems:"center",gap:6,
                  padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",userSelect:"none",
                  transition:"all .15s",
                  background: filter==="tx" ? `${rxColor}18` : "var(--surface2)",
                  border: `1px solid ${filter==="tx" ? rxColor+"60" : "var(--border)"}`,
                  opacity: filter==="rx" ? 0.35 : 1,
                  color: filter==="tx" ? rxColor : "var(--muted)"}}>
                <span style={{width:14,height:2,background:rxColor,borderRadius:1,display:"inline-block"}}/>
                ↓ Скачивание
              </span>
              {/* ↑ Отдача toggle */}
              <span onClick={()=>setFilter(f=>f==="rx"?"both":"rx")}
                style={{display:"inline-flex",alignItems:"center",gap:6,
                  padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",userSelect:"none",
                  transition:"all .15s",
                  background: filter==="rx" ? `${txColor}18` : "var(--surface2)",
                  border: `1px solid ${filter==="rx" ? txColor+"60" : "var(--border)"}`,
                  opacity: filter==="tx" ? 0.35 : 1,
                  color: filter==="rx" ? txColor : "var(--muted)"}}>
                <span style={{width:14,height:2,background:txColor,borderRadius:1,display:"inline-block",opacity:.85}}/>
                ↑ Отдача
              </span>
              {filter!=="both"&&(
                <span onClick={()=>setFilter("both")}
                  style={{display:"inline-flex",alignItems:"center",gap:4,
                    padding:"4px 10px",borderRadius:"var(--radius)",cursor:"pointer",userSelect:"none",
                    border:"1px solid var(--border)",color:"var(--muted)",fontSize:12,
                    background:"var(--surface2)"}}>
                  оба
                </span>
              )}
            </div>
          </div>
      }
    </div>
  );
};

// Gauge removed — shown in sidebar WMD widget

