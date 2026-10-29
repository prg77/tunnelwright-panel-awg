import React, { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";
import { UserLink } from "../components/UserLink";

// ─── QR Modal ─────────────────────────────────────────────────────
export const QRModal = ({ client, onClose }) => {
  const [svg,setSvg]=useState(null);
  const [err,setErr]=useState("");
  const [copied,setCopied]=useState(false);
  const [full,setFull]=useState(false);
  const [dlQr,setDlQr]=useState(false);
  const ip=(client.ip||"").replace("/32","");
  // Профиль на каждой ноде — свой конфиг и QR
  const profiles=client.nodes||[];
  const [node,setNode]=useState(profiles[0]?.id??null);
  const nodeName=profiles.find(p=>p.id===node)?.name;
  useEffect(()=>{
    let dead=false;
    setSvg(null); setErr("");
    api.qr(client.id, node).then(s=>{ if(!dead) setSvg(s); }).catch(e=>{ if(!dead) setErr(e.message); });
    return()=>{ dead=true; };
  },[client.id, node]);

  // имя файла задаёт сервер (имя клиента и ноды, в том числе кириллицей)
  const dl=()=>{ const a=document.createElement("a"); a.href=api.confUrl(client.id, node); a.download=""; a.click(); };

  // ── Скачать QR как PNG ────────────────────────────────────────────
  const downloadQrPng = () => {
    if (!svg) return;
    setDlQr(true);
    try {
      const SIZE = 512;
      const svgClean = svg
        .replace(/width="[^"]*"/, `width="${SIZE}"`)
        .replace(/height="[^"]*"/, `height="${SIZE}"`);

      // Используем data: URL вместо blob: — нет предупреждения "insecure connection"
      const svgDataUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgClean);
      const img  = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = SIZE + 48; canvas.height = SIZE + 80;
        const ctx = canvas.getContext("2d");

        ctx.fillStyle = "#ffffff";
        ctx.roundRect(0, 0, canvas.width, canvas.height, 16);
        ctx.fill();
        ctx.drawImage(img, 24, 24, SIZE, SIZE);

        ctx.fillStyle = "#111111";
        ctx.font = "bold 18px 'Inter',system-ui,sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(client.name, canvas.width/2, SIZE + 52);
        ctx.font = "14px 'Courier New',monospace";
        ctx.fillStyle = "#555555";
        ctx.fillText(nodeName ? `${ip} · ${nodeName}` : ip, canvas.width/2, SIZE + 70);

        canvas.toBlob(pngBlob => {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(pngBlob);
          a.download = `vpn-qr-${client.name||"client"}${nodeName ? "-" + nodeName : ""}.png`.replace(/[\\/:*?"<>|]/g,"_");
          a.click();
          setTimeout(() => URL.revokeObjectURL(a.href), 1000);
          setDlQr(false);
        }, "image/png");
      };
      img.onerror = () => { setDlQr(false); };
      img.src = svgDataUrl;
    } catch(e) { setDlQr(false); }
  };

  const copyMsg=()=>{
    const msg=[
      `🔐 Ваш VPN-доступ готов`,
      `━━━━━━━━━━━━━━━━━━━━━━━`,
      `👤 Имя: ${client.name}`,
      `🌐 IP:  ${ip}`,
      `🛡️  Протокол: AmneziaWG (обфусцированный)`,
      ``,
      `📲 Установите приложение AmneziaWG:`,
      ``,
      `  🤖 Android — Google Play:`,
      `  https://play.google.com/store/apps/details?id=org.amnezia.awg`,
      ``,
      `  🍎 iOS / macOS — App Store:`,
      `  https://apps.apple.com/app/amneziawg/id6478942365`,
      ``,
      `  🪟 Windows:`,
      `  https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest`,
      ``,
      `  🐧 Linux (GUI):`,
      `  https://github.com/amnezia-vpn/amneziawg-tools`,
      ``,
      `📋 Подключение:`,
      `  Откройте приложение → нажмите + → Сканировать QR-код`,
      `  или импортируйте .conf файл`,
      ``,
      `━━━━━━━━━━━━━━━━━━━━━━━`,
      `Отправлено через AmneziaWG Admin Panel`
    ].join("\n");
    const w=(t)=>{ if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(t); const e=document.createElement("textarea"); e.value=t; e.style.cssText="position:fixed;opacity:0"; document.body.appendChild(e); e.select(); try{document.execCommand("copy");}catch{} document.body.removeChild(e); return Promise.resolve(); };
    w(msg).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),3000);}).catch(()=>{});
  };
  return(<>
    {full&&svg&&<div onClick={()=>setFull(false)} style={{position:"fixed",inset:0,background:"rgba(0,0,0,.98)",zIndex:9999,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:24}}>
      <div style={{background:"#fff",borderRadius:"var(--radius-lg)",padding:24}} dangerouslySetInnerHTML={{__html:svg.replace(/width="[^"]*"/,'width="340"').replace(/height="[^"]*"/,'height="340"')}}/>
      <div style={{color:"rgba(255,255,255,.4)",fontSize:14}}>нажмите чтобы закрыть</div>
    </div>}
    <div style={{position:"fixed",inset:0,background:"var(--overlay-bg)",backdropFilter:"blur(8px)",zIndex:9990,display:"flex",alignItems:"center",justifyContent:"center",padding:16}} onClick={onClose}>
      <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:24,maxWidth:380,width:"100%",animation:"pop .22s ease",maxHeight:"94vh",overflowY:"auto"}} onClick={e=>e.stopPropagation()}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16}}>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontWeight:700,fontSize:15}}>{client.name}{client.uid&&<span title="ID клиента" style={{marginLeft:7,fontSize:12,fontWeight:400,color:"var(--muted)",fontFamily:"var(--mono)"}}>#{client.uid}</span>}</div>
            <div style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>{ip}</div>
          </div>
          <button onClick={copyMsg} title="Скопировать инструкцию" style={{
            padding:"6px 10px",
            background:copied?"color-mix(in srgb,var(--success) 15%,transparent)":"var(--surface2)",
            border:copied?"1px solid color-mix(in srgb,var(--success) 50%,transparent)":"1px solid var(--border)",
            borderRadius:"var(--radius)",cursor:"pointer",
            transition:"all .22s cubic-bezier(.34,1.56,.64,1)",
            flexShrink:0,display:"flex",alignItems:"center",gap:5,
            
            transform:copied?"scale(1.05)":"scale(1)"
          }}>
            {copied
              ? <span style={{color:"var(--success)",fontSize:14,animation:"checkPop .3s cubic-bezier(.34,1.56,.64,1)"}}>✓</span>
              : <span style={{fontSize:14,lineHeight:1}}>⧉</span>
            }
            <span style={{fontSize:12,fontWeight:600,color:copied?"var(--success)":"var(--muted)"}}>
              {copied?"Готово":"Текст"}
            </span>
          </button>
          <button onClick={onClose} style={{background:"none",border:"none",color:"var(--muted)",cursor:"pointer",fontSize:19,padding:"0 4px",flexShrink:0}}>✕</button>
        </div>

        {/* Ноды: у клиента профиль на каждой */}
        {profiles.length>1&&<div style={{display:"flex",gap:4,flexWrap:"wrap",marginBottom:12}}>
          {profiles.map(p=>(<button key={p.id} onClick={()=>setNode(p.id)} style={{flex:"1 1 auto",padding:"6px 10px",borderRadius:"var(--radius)",
            cursor:"pointer",fontSize:12,fontWeight:600,border:`1px solid ${node===p.id?"var(--cyan)":"var(--border)"}`,
            background:node===p.id?"var(--surface2)":"transparent",color:node===p.id?"var(--cyan)":"var(--muted)"}}>{p.name}</button>))}
        </div>}
        {profiles.length===0&&<div style={{fontSize:12,color:"var(--warning)",marginBottom:10}}>Профили ещё создаются на нодах — откройте окно через минуту.</div>}

        {/* QR Block */}
        {!svg&&!err&&profiles.length>0&&<div style={{display:"flex",justifyContent:"center",padding:40}}><div style={{width:28,height:28,border:"2px solid var(--border)",borderTopColor:"var(--cyan)",borderRadius:"50%",animation:"spin .7s linear infinite"}}/></div>}
        {err&&<div style={{color:"var(--error)",fontSize:14,padding:"16px 0",textAlign:"center"}}>{err}</div>}
        {svg&&(
          <div style={{marginBottom:14}}>
            {/* QR + fullscreen overlay */}
            <div style={{position:"relative"}}>
              <div
                style={{background:"#fff",borderRadius:"var(--radius-lg)",padding:14,display:"flex",justifyContent:"center",cursor:"pointer"}}
                onClick={()=>setFull(true)}
                title="Нажмите для увеличения"
              >
                <div dangerouslySetInnerHTML={{__html:svg.replace(/width="[^"]*"/,'width="230"').replace(/height="[^"]*"/,'height="230"')}}/>
              </div>
              <div style={{position:"absolute",top:8,right:8,display:"flex",gap:5}}>
                <button onClick={()=>setFull(true)} style={{padding:"4px 8px",background:"rgba(0,0,0,.6)",border:"1px solid rgba(255,255,255,.15)",borderRadius:"var(--radius)",color:"rgba(255,255,255,.8)",fontSize:12,cursor:"pointer",backdropFilter:"blur(4px)"}}>⛶</button>
              </div>
            </div>

            {/* PNG download — главная кнопка */}
            <button
              onClick={downloadQrPng}
              disabled={dlQr}
              className={dlQr?"":"btn-glow btn-primary-glow"}
              style={{width:"100%",marginTop:8,padding:"10px 0",
                background:"var(--primary)",border:"none",borderRadius:"var(--radius-lg)",
                color:"#fff",fontSize:14,fontWeight:700,cursor:dlQr?"wait":"pointer",
                display:"flex",alignItems:"center",justifyContent:"center",gap:7,
                opacity:dlQr?.7:1,transition:"all .2s",
                boxShadow:`0 4px 18px rgba(var(--cyan-rgb,99 102 241)/.3)`}}>
              {dlQr
                ? <><span style={{width:13,height:13,border:"2px solid rgba(0,0,0,.3)",borderTopColor:"#fff",borderRadius:"50%",animation:"spin .7s linear infinite",flexShrink:0}}/> Готовлю PNG...</>
                : <>Скачать QR как PNG</>}
            </button>
            <div style={{marginTop:5,fontSize:12,color:"var(--muted)",textAlign:"center",lineHeight:1.5}}>
              PNG готов к отправке в Telegram · без скриншотов
            </div>
          </div>
        )}

        <UserLink client={client}/>

        {/* App links — all platforms */}
        <div style={{marginBottom:14,background:"var(--bg)",borderRadius:"var(--radius-lg)",padding:"10px 12px"}}>
          <div style={{fontSize:11,color:"var(--muted)",fontWeight:700,marginBottom:8}}>Скачать AmneziaWG</div>
          {[
            {icon:"🤖",name:"Android",sub:"Google Play",url:"https://play.google.com/store/apps/details?id=org.amnezia.awg"},
            {icon:"🍎",name:"iOS / macOS",sub:"App Store",url:"https://apps.apple.com/app/amneziawg/id6478942365"},
            {icon:"🪟",name:"Windows",sub:"GitHub Releases",url:"https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest"},
            {icon:"🐧",name:"Linux",sub:"amneziawg-tools",url:"https://github.com/amnezia-vpn/amneziawg-tools"},
          ].map(a=>(<a key={a.name} href={a.url} target="_blank" rel="noreferrer" className="btn-glow"
            style={{display:"flex",alignItems:"center",gap:9,padding:"7px 10px",borderRadius:"var(--radius)",
              marginBottom:4,background:"rgba(255,255,255,.025)",border:"1px solid var(--border)",
              color:"var(--text)",textDecoration:"none",fontSize:14,transition:"all .18s"}}>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontWeight:600,fontSize:14}}>{a.name}</div>
              <div style={{fontSize:11,color:"var(--muted)",marginTop:1}}>{a.sub}</div>
            </div>
            <span style={{fontSize:12,opacity:.35,flexShrink:0}}>↗</span>
          </a>))}
          <div style={{marginTop:8,padding:"7px 10px",background:"var(--border)",
            borderRadius:"var(--radius)",border:"1px solid var(--border)",fontSize:12,color:"var(--muted)",lineHeight:1.6}}>
            <span style={{color:"var(--cyan)",fontWeight:600}}>Подключение:</span> Открыть приложение → <span style={{color:"var(--text)"}}>+</span> → Сканировать QR-код или импортировать .conf
          </div>
        </div>

        {/* Footer actions */}
        <div style={{display:"flex",gap:8}}>
          <button onClick={dl} className="btn-glow" style={{flex:1,padding:"10px 0",
            background:"color-mix(in srgb,var(--cyan) 12%,transparent)",
            border:"1px solid color-mix(in srgb,var(--cyan) 35%,transparent)",
            borderRadius:"var(--radius)",color:"var(--cyan)",fontSize:14,fontWeight:600,cursor:"pointer",
            transition:"all .18s",display:"flex",alignItems:"center",justifyContent:"center",gap:6}}>
            <span style={{fontSize:14}}>⬇</span> .conf файл
          </button>
          <button onClick={onClose} className="btn-glow" style={{padding:"10px 16px",
            background:"var(--surface2)",border:"1px solid var(--border)",
            borderRadius:"var(--radius)",color:"var(--muted)",fontSize:14,cursor:"pointer",
            transition:"all .18s"}}>Закрыть</button>
        </div>
      </div>
    </div>
  </>);
};
