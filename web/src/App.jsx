import React, { useState, useEffect, useRef, useCallback } from "react";
import { fmtClock, getPanelTz, setPanelTz } from "./utils/time";
import { api } from "./api";
import { AuditLog } from "./components/AuditLog";
import { useNotify } from "./components/Notify";
import { SideNav } from "./components/SideNav";
import { TrafficChart } from "./components/TrafficChart";
import { Card, CardH, Btn } from "./components/ui";
import { ConfirmModal } from "./modals/ConfirmModal";
import { LimitModal } from "./modals/LimitModal";
import { MetaModal } from "./modals/MetaModal";
import { QRModal } from "./modals/QRModal";
import { RoutingModal } from "./modals/RoutingModal";
import { AddClientPage } from "./pages/AddClientPage";
import { ListsPage } from "./pages/ListsPage";
import { NodesPage } from "./pages/NodesPage";
import { BackupCard } from "./settings/BackupCard";
import { BotCard } from "./settings/BotCard";
import { GroupsCard } from "./settings/GroupsCard";
import { PortalNameCard } from "./settings/PortalNameCard";
import { ResetTrafficCard } from "./settings/ResetTrafficCard";
import { SecurityCard } from "./settings/SecurityCard";
import { TimezoneCard } from "./settings/TimezoneCard";
import { TelegramCard } from "./settings/TelegramCard";
import { UserPageCard } from "./settings/UserPageCard";
import { clientUsageStore } from "./stores/clientUsage";
import { groupsStore, useGroups } from "./stores/groups";
import { TH_KEY, thStore } from "./stores/trafficHistory";
import { ONLINE_MS, APP_VERSION, THEMES } from "./theme/constants";
import { fmtBytes, fmtGB, aColor } from "./utils/format";
import { getLastOctet, getPrefix } from "./utils/ip";


// ═══════════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════════

// ─── Глобальные стили (стиль Grafana; цвета — theme/tokens.css) ──────
const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Roboto+Mono:wght@400;500&display=swap');
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  html{scrollbar-gutter:stable}
  body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.5}
  ::-webkit-scrollbar{width:8px;height:8px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border-medium);border-radius:4px}
  ::selection{background:color-mix(in srgb,var(--primary) 35%,transparent)}

  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes pop{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @keyframes fadeIn{from{opacity:0}to{opacity:1}}
  @keyframes nIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  @keyframes sideIn{from{transform:translateX(-100%)}to{transform:none}}
  @keyframes slideDown{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
  @keyframes checkPop{from{transform:scale(0)}to{transform:scale(1)}}
  @keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}

  /* ── Поля ввода: высота 32px, радиус 2px, фокус — двойное кольцо ── */
  input,select,textarea{font-family:var(--sans);font-size:14px;color:var(--text)}
  input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]),select,textarea{
    background:var(--input-bg)!important;border:1px solid var(--border-medium)!important;
    border-radius:var(--radius)!important;color:var(--text)!important;outline:none;
    transition:border-color .15s,box-shadow .15s}
  input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]),select{min-height:32px;padding:0 8px}
  input:hover,select:hover,textarea:hover{border-color:var(--border-strong)!important}
  input:focus,select:focus,textarea:focus{box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--primary)!important;border-color:var(--border-medium)!important}
  input.invalid{border-color:var(--error)!important}
  input::placeholder,textarea::placeholder{color:var(--disabled)}
  input[type=checkbox],input[type=radio]{accent-color:var(--primary)}
  .field{display:flex;flex-direction:column;gap:4px}
  .field>span{font-size:14px;font-weight:500;color:var(--text)}
  .field>input{width:100%}

  /* ── Кнопки ── */
  .btn{border:1px solid transparent;transition:background .15s,border-color .15s,color .15s}
  .btn:focus-visible{outline:none;box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--primary)}
  .btn-primary{background:var(--primary);color:#fff}
  .btn-primary:not(:disabled):hover{background:var(--primary-hover)}
  .btn-ghost,.btn-icon{background:var(--surface2);color:var(--text);border-color:var(--border-medium)}
  .btn-icon{color:var(--muted)}
  .btn-ghost:not(:disabled):hover,.btn-icon:not(:disabled):hover{background:var(--action-hover);color:var(--text)}
  .btn-danger{background:transparent;color:var(--error);border-color:color-mix(in srgb,var(--error) 45%,transparent)}
  .btn-danger:not(:disabled):hover{background:var(--error-main);border-color:var(--error-main);color:#fff}
  .btn-amber{background:transparent;color:var(--warning);border-color:color-mix(in srgb,var(--warning) 45%,transparent)}
  .btn-amber:not(:disabled):hover{background:color-mix(in srgb,var(--warning) 14%,transparent)}
  .btn-glow{transition:background .15s,filter .15s}
  .btn-glow:not(:disabled):hover{filter:brightness(1.1)}

  /* ── Уведомление в форме ── */
  .alert{padding:8px 12px;border-radius:var(--radius);font-size:14px;border-left:4px solid}
  .alert-error{background:color-mix(in srgb,var(--error-main) 16%,transparent);border-color:var(--error-main);color:var(--text)}

  /* ── Строки таблиц ── */
  .rh{transition:background .1s}
  .rh:hover{background:var(--row-hover)!important}
  .th{font-size:12px;font-weight:500;color:var(--muted)}

  /* ── Боковое меню ── */
  .nav-section{padding:8px 16px 4px;font-size:12px;font-weight:500;color:var(--muted)}
  .nav-item{position:relative;display:flex;align-items:center;gap:12px;width:100%;height:32px;
    padding:0 16px;border:none;background:transparent;color:var(--muted);cursor:pointer;
    font-family:var(--sans);font-size:14px;text-align:left;white-space:nowrap}
  .nav-item:hover{background:var(--nav-hover);color:var(--text)}
  .nav-item:focus-visible{outline:none;box-shadow:inset 0 0 0 2px var(--primary)}
  .nav-active{background:var(--nav-active-bg);color:var(--text);font-weight:500}
  .nav-active::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:4px;border-radius:2px;background:var(--nav-indicator)}
  .nav-icon{display:flex;align-items:center;justify-content:center;width:16px;flex-shrink:0}
  .nav-icon svg{display:block}
  .nav-count{font-size:12px;font-family:var(--mono);color:var(--muted);background:var(--surface2);
    border:1px solid var(--border);border-radius:var(--radius);padding:0 6px;line-height:18px}

  /* ── Шапка ── */
  .tb-btn{display:flex;align-items:center;justify-content:center;width:32px;height:32px;border:none;
    border-radius:var(--radius);background:transparent;color:var(--muted);cursor:pointer}
  .tb-btn:hover{background:var(--action-hover);color:var(--text)}
  .crumb{color:var(--muted);text-decoration:none;cursor:pointer;background:none;border:none;font:inherit}
  .crumb:hover{color:var(--text);text-decoration:underline}

  .radio-group{display:inline-flex;border:1px solid var(--border-medium);border-radius:var(--radius);overflow:hidden}
  .radio-group button{height:24px;padding:0 8px;font-size:12px;font-family:var(--sans);background:transparent;border:none;color:var(--muted);cursor:pointer}
  .radio-group button+button{border-left:1px solid var(--border-medium)}
  .radio-group button:hover{color:var(--text)}
  .radio-group button.on{background:var(--action-selected);color:var(--text);font-weight:500}

  .gpill{transition:background .15s}
  .gpill:hover{background:var(--action-hover)!important}

  .desktop-sb{display:flex}
  .mob-btn{display:none}

  @media(max-width:768px){
    .desktop-sb{display:none!important}
    .mob-btn{display:flex!important}
    .hide-mob{display:none!important}
    .grid-4{grid-template-columns:1fr 1fr!important}
    .grid-2,.grid-2-3{grid-template-columns:1fr!important}
    .topbar-strip{display:none!important}
    .dash-bottom{flex-direction:column!important}
    .top3-grid{flex-direction:column!important;gap:8px!important}
    .top3-box{flex:none!important;width:100%!important}
    .traffic-stats-row{grid-template-columns:1fr 1fr!important}
    .traffic-legend{flex-wrap:wrap!important}
    main{padding:12px 8px 24px!important}
    header{padding:0 8px!important}
    .wide-page,.page-form{max-width:100%!important;padding:0}
    .limit-modal-inner,.meta-modal-inner,.qr-modal-inner{max-width:calc(100vw - 16px)!important;margin:8px!important}
  }
  @media(max-width:480px){
    .topbar-clock,.crumb-host{display:none!important}
    .page-title-sub{display:none!important}
    .clients-toolbar{flex-wrap:wrap!important;gap:5px!important}
  }
`;

// Логотип Tunnelwright: гора со светящимся туннелем в треугольнике (branding/).
// Мелкий размер — упрощённая иконка, крупный — эмблема с гранями; рамка — по теме (--logo-frame)
const Logo = ({size=24}) => {
  const id = React.useId();
  const frame = "var(--logo-frame)";
  if (size < 40) return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <defs><clipPath id={id}><polygon points="50,16 85,87 15,87"/></clipPath></defs>
      <g clipPath={`url(#${id})`}>
        <polygon points="10,90 32,58 52,20 70,50 90,90" fill="#1E3B30"/>
        <polygon points="52,20 44,46 38,90 54,90 50,62 58,42" fill="#4E8C6A"/>
        <polygon points="70,50 62,66 70,90 90,90" fill="#2E6450"/>
        <path d="M39 90V75a11 11 0 0 1 22 0V90Z" fill="#F2C14E"/>
      </g>
      <polygon points="50,5 94,93 6,93" fill="none" stroke={frame} strokeWidth="6"/>
    </svg>
  );
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <defs><clipPath id={id}><polygon points="50,12 88,89 12,89"/></clipPath></defs>
      <g clipPath={`url(#${id})`}>
        <polygon points="16,90 28,66 33,70 44,40 47,44 54,22 60,40 64,36 72,54 76,52 86,90" fill="#1E3B30"/>
        <polygon points="54,22 49,40 52,46 45,58 49,64 41,76 43,90 57,90 52,80 57,70 53,60 57,48 55,38" fill="#4E8C6A"/>
        <polygon points="54,22 51,32 54,36 55,30" fill="#7DB894"/>
        <polygon points="60,40 58,52 64,60 61,70 68,90 86,90 76,52 72,54 64,36" fill="#2E6450"/>
        <polygon points="33,70 28,66 16,90 30,90 34,80 30,76" fill="#2E6450"/>
        <path d="M60 40L58 52L64 60L61 70L68 90M33 70L30 76L34 80L30 90M72 54L70 64L75 72" fill="none" stroke="#15291F" strokeWidth="1.4" strokeLinejoin="round"/>
        <path d="M42 90V79a8 8 0 0 1 16 0V90Z" fill="#F2C14E"/>
        <path d="M45.5 90V80.5a4.5 4.5 0 0 1 9 0V90Z" fill="#FFE29A"/>
      </g>
      <polygon points="50,5 93,92 7,92" fill="none" stroke={frame} strokeWidth="3.4"/>
    </svg>
  );
};
const SUN = <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
const MOON = <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>;
const fmtBits = (kbs) => { const b=(kbs||0)*1024*8; if(!b||isNaN(b))return"0 бит/с"; if(b>=1e9)return(b/1e9).toFixed(2)+" Гбит/с"; if(b>=1e6)return(b/1e6).toFixed(2)+" Мбит/с"; if(b>=1e3)return(b/1e3).toFixed(1)+" Кбит/с"; return Math.round(b)+" бит/с"; };


// Иконки действий (контурные 16px, как в Grafana)
const svg16 = (children) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;
const IC = {
  qr:    svg16(<><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h3v-3"/></>),
  edit:  svg16(<><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></>),
  route: svg16(<><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></>),
  pause: svg16(<><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></>),
  play:  svg16(<polygon points="6 4 20 12 6 20 6 4"/>),
  trash: svg16(<><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></>),
  gauge: svg16(<><path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/></>),
};
// Бейдж-метка: полупрозрачный фон цвета метки, как Tag в Grafana
const tag = (c) => ({fontSize:12,lineHeight:"18px",padding:"0 6px",borderRadius:"var(--radius)",flexShrink:0,whiteSpace:"nowrap",fontWeight:500,
  color:c,background:`color-mix(in srgb,${c} 14%,transparent)`,border:`1px solid color-mix(in srgb,${c} 35%,transparent)`});

const PAGE_IDS = ["dashboard","clients","add","lists","nodes","logs","settings"];

function App() {
  const [authed,setAuthed]=useState(false);
  const [authBusy,setAuthBusy]=useState(true);
  // Логин не подставляется: поле пустое при каждом открытии страницы входа
  const [lUser,setLUser]=useState("");
  const [lPass,setLPass]=useState("");
  const [lTotp,setLTotp]=useState("");
  const [needTotp,setNeedTotp]=useState(false);
  const [lErr,setLErr]=useState("");
  const [lBusy,setLBusy]=useState(false);
  const [page,setPage]=useState(()=>{ const h=window.location.hash.replace("#",""); return PAGE_IDS.includes(h)?h:"dashboard"; });
  const [sideOpen,setSideOpen]=useState(false);
  const [sideCollapsed,setSideCollapsed]=useState(false);
  useEffect(()=>{window.location.hash=page;},[page]);
  // «Назад»/«Вперёд» в браузере меняют только hash — переключаем раздел следом
  useEffect(()=>{
    const onHash=()=>{ const h=window.location.hash.replace("#",""); if(PAGE_IDS.includes(h)) setPage(h); };
    window.addEventListener("hashchange",onHash);
    return ()=>window.removeEventListener("hashchange",onHash);
  },[]);
  const [theme,setTheme]=useState(()=>{ try{const t=localStorage.getItem("awg-theme")||"dark";return t==="light"?"light":"dark";}catch{return"dark";} });
  const [clients,setClients]=useState([]);
  const [cBusy,setCBusy]=useState(false);
  const [cErr,setCErr]=useState("");
  const [stats,setStats]=useState(null);
  // Настройки панели: имя, часовой пояс, адрес и порты (GET /api/settings)
  const [config,setConfig]=useState({wg_host:"",web_port:0,wg_port:null});
  const [tg,setTg]=useState(null);   // состояние уведомлений Telegram (без токена)
  const [qrClient,setQrClient]=useState(null);
  // Лимиты и метаданные приходят в самих клиентах — здесь только удобные срезы для страниц
  const limits = Object.fromEntries(clients.filter(c=>c.limit).map(c=>[c.ip, c.limit]));
  const clientMeta = Object.fromEntries(clients.map(c=>[c.id, {group:c.group||undefined, note:c.note,
    expiresAt:c.expiresAt||undefined, createdAt:c.createdAt&&c.createdAt.replace(" ","T")+"Z"}]));   // created_at — UTC из SQLite
  const [editLimit,setEditLimit]=useState(null);
  const [editMeta,setEditMeta]=useState(null);
  const [editRouting,setEditRouting]=useState(null);
  const [routingAll,setRoutingAll]=useState({}); // {id: {net_mode, app_mode, custom}}
  const { names: GROUPS, colors: GC } = useGroups();
  const loadRouting=useCallback(()=>api.routingAll().then(setRoutingAll).catch(()=>{}),[]);
  const [confirmModal,setConfirmModal]=useState(null); // {title, detail, onConfirm}
  const [filterGroup,setFilterGroup]=useState("all");
  const [searchQ,setSearchQ]=useState("");
  const [trafficPts, setTrafficPts] = useState(() => thStore.load());
  const [txSpd, setTxSpd] = useState(0);
  const [rxSpd, setRxSpd] = useState(0);
  const [trafficPeriod, setTrafficPeriod] = useState("1h");
  const [clientUsage, setClientUsage] = useState(()=>clientUsageStore.load()); // кэш из localStorage, затем с сервера

  useEffect(()=>{ if(!authed) return; groupsStore.reload(); loadRouting(); },[authed, loadRouting]);
  const prevT=useRef(null);
  const {push,Stack}=useNotify();
  const [clock,setClock]=useState(()=>fmtClock());
  useEffect(()=>{ const t=setInterval(()=>setClock(fmtClock()),1000); return()=>clearInterval(t); },[]);

  // Синхронизация истории трафика между вкладками
  useEffect(()=>{
    const onStorage = (e) => {
      if(e.key === TH_KEY) setTrafficPts(thStore.load());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const T=THEMES[theme]||THEMES.dark;

  // CSS-переменные темы — в theme/tokens.css, здесь только переключаем data-theme
  useEffect(()=>{
    try{localStorage.setItem("awg-theme",theme);}catch{}
    document.documentElement.dataset.theme = theme;
  },[theme]);


  useEffect(()=>{
    let c=false;
    // Retry session check — wg-easy может ещё стартовать (502) при первой загрузке
    const check = async (attempt=0) => {
      if(c) return;
      try {
        const s = await api.session();
        if(!c && s?.authenticated) setAuthed(true);
      } catch {
        // 502/сеть — retry через 3с, максимум 10 попыток
        if(!c && attempt < 10) setTimeout(()=>check(attempt+1), 3000);
      } finally {
        if(!c && attempt===0) setAuthBusy(false); // убираем спиннер сразу после первой попытки
      }
    };
    check();
    return()=>{c=true;};
  },[]);
  const doLogin=async()=>{
    setLBusy(true);setLErr("");
    try{
      await api.login(lUser.trim(), lPass, needTotp ? lTotp : undefined);
      try{localStorage.removeItem("awg-login");}catch{}   // логин, сохранённый прежними версиями
      setNeedTotp(false);setLTotp("");setAuthed(true);
    }catch(e){
      if(e.needTotp){ setNeedTotp(true); setLErr(needTotp ? e.message : ""); }
      else setLErr(e.message||"Неверный логин или пароль");
    }finally{setLBusy(false);}
  };
  const doLogout=async()=>{ await api.logout().catch(()=>{}); setAuthed(false);setClients([]);setLPass("");setLTotp("");setNeedTotp(false); };

  // Настройки, Telegram и трафик — при входе
  useEffect(()=>{ if(!authed)return; let c=false;
    api.settings().then(s=>{ if(c) return; setPanelTz(s.timezone); setConfig(s); }).catch(()=>{});
    api.telegram().then(t=>{ if(!c) setTg(t); }).catch(()=>{});
    thStore.loadFromServer().then(pts=>{ if(!c&&pts) setTrafficPts([...pts]); });
    clientUsageStore.loadFromServer().then(d=>{ if(!c&&d) setClientUsage({...d}); });
    return()=>{c=true;};
  },[authed]);

  const loadClients=useCallback(async()=>{
    setCBusy(true); setCErr("");
    try { setClients(await api.clients()||[]); }
    catch(e) { setCErr(e.message); }
    finally { setCBusy(false); }
  },[]);
  useEffect(()=>{ if(!authed)return; let cancel=false;
    loadClients();
    let errSkip=0; // после ошибки пропускаем несколько опросов (до ~30 с)
    const poll=async()=>{ if(cancel)return;
      if(errSkip>0){errSkip--;return;}
      try{
      const cls=await api.clients(); if(cancel)return; setClients(cls||[]);
      errSkip=0;
      const now=Date.now(); let tx=0,rx=0;
      (cls||[]).forEach(c=>{tx+=c.tx||0;rx+=c.rx||0;});
      // Суточную статистику клиентов считает сервер — здесь только скорость и живой график
      if(prevT.current){ const dt=(now-prevT.current.ts)/1000;
        const tS=Math.max(0,(tx-prevT.current.tx)/dt);
        const rS=Math.max(0,(rx-prevT.current.rx)/dt);
        if(!cancel){
          setTxSpd(tS/1024);
          setRxSpd(rS/1024);
          setTrafficPts([...thStore.push(now, tx, rx)]);
        }
      }
      prevT.current={tx,rx,ts:now};
    }catch{ errSkip=Math.min(errSkip+3,9); } };
    const t=setInterval(poll,3000); poll();
    return()=>{cancel=true;clearInterval(t);};
  },[authed,loadClients]);

  useEffect(()=>{ if(!authed)return; let c=false;
    const poll=async()=>{if(c)return;try{const s=await api.stats();if(!c)setStats(s);}catch{}};
    const t=setInterval(poll,12000); poll(); // каждые 12с — актуальные RAM/DISK
    return()=>{c=true;clearInterval(t);};
  },[authed]);

  // Суточный трафик клиентов с сервера — раз в 30 с
  useEffect(()=>{ if(!authed)return; let c=false;
    const t=setInterval(()=>{
      clientUsageStore.loadFromServer().then(d=>{if(!c&&d)setClientUsage({...d});});
    }, 30000);
    return()=>{c=true;clearInterval(t);};
  },[authed]);

  const online =clients.filter(c=>c.enabled&&c.handshakeAt&&(Date.now()-new Date(c.handshakeAt))<ONLINE_MS).length;
  const active =clients.filter(c=>c.enabled).length;
  const totalTx=clients.reduce((s,c)=>s+(c.tx||0),0);
  const totalRx=clients.reduce((s,c)=>s+(c.rx||0),0);

  // Изменения клиентов: сервер применяет их на всех нодах и сам шлёт уведомления в Telegram
  const putClient = (c) => setClients(cs => cs.map(x => x.id===c.id ? c : x));
  const toggleClient=async(c)=>{ try{
    putClient(await api.patchClient(c.id, {enabled:!c.enabled}));
    push({type:c.enabled?"warn":"ok",title:`${c.name} ${c.enabled?"отключён":"включён"}`,
      detail:c.enabled?"Клиент потерял доступ к VPN":"Клиент подключён к VPN"});
  }catch(e){push({type:"err",title:"Не изменено",detail:e.message});} };
  const delClient = (c) => setConfirmModal({
    title: `Удалить «${c.name}»?`,
    detail: `Профили на всех нодах будут удалены, IP ${c.ip} освобождён, лимит снят.`,
    onConfirm: async () => {
      try {
        await api.delClient(c.id);
        setClients(cs => cs.filter(x => x.id !== c.id));
        push({type:"warn",title:`${c.name} удалён`,detail:`IP ${c.ip} освобождён`});
      } catch(e) { push({type:"err",title:"Не удалено",detail:e.message}); }
    }
  });
  const updateLimit = async (id, down, up) => {
    const c = clients.find(x => x.id===id);
    try {
      const r = await api.setLimit(id, {down:+down, up:+up});
      setClients(cs => cs.map(x => x.id===id ? {...x, limit:r.limit} : x));
      push(r.errors?.length
        ? {type:"warn", title:"Лимит сохранён", detail:`Не все ноды применили: ${r.errors.join("; ")}`}
        : {type:"ok", title:`Лимит · ${c?.name||""}`, detail:`↓${down} ↑${up} Мбит/с`});
    } catch(e) { push({type:"err", title:"Лимит не сохранён", detail:e.message}); }
  };
  const removeLimit = async (id) => {
    const c = clients.find(x => x.id===id);
    try {
      await api.delLimit(id);
      setClients(cs => cs.map(x => x.id===id ? {...x, limit:null} : x));
      push({type:"warn", title:`Лимит снят · ${c?.name||""}`, detail:"Скорость без ограничений"});
    } catch(e) { push({type:"err", title:"Лимит не снят", detail:e.message}); }
  };
  const saveMeta=async(id,patch)=>{
    const c=clients.find(x=>x.id===id);
    if(!c) return;
    const p={note:patch.note??"", group:patch.group&&patch.group!=="Без группы"?patch.group:"", expiresAt:patch.expiresAt||null};
    const oct=patch.ipLastOctet;
    if(oct!==undefined&&oct!==getLastOctet(c.ip)) p.ip=`${getPrefix(c.ip)}.${oct}`;
    try{
      putClient(await api.patchClient(id, p));
      push(p.ip ? {type:"ok",title:"IP изменён",detail:`${c.name}: ${c.ip} → ${p.ip}`} : {type:"ok",title:"Сохранено",detail:c.name});
    }catch(e){ push({type:"err",title:"Не сохранено",detail:e.message}); }
  };

  // ─── UI atoms ────────────────────────────────────────────────────
  const KV=({k,v,vc})=>(<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 0",borderBottom:"1px solid var(--border)",fontSize:14,gap:8}}>
    <span style={{color:"var(--muted)",flexShrink:0}}>{k}</span>
    <span style={{fontFamily:"var(--mono)",color:vc||"var(--text)",textAlign:"right",wordBreak:"break-all"}}>{v}</span>
  </div>);
  // Loading
  if(authBusy)return(<div style={{minHeight:"100vh",background:"var(--bg)",display:"flex",alignItems:"center",justifyContent:"center"}}><style>{GLOBAL_CSS}</style><div style={{width:32,height:32,border:"3px solid var(--border-medium)",borderTopColor:"var(--primary)",borderRadius:"50%",animation:"spin .8s linear infinite"}}/></div>);

  // Login
  // portal_name: сервер → localStorage fallback → "Private World"
  const portalName = (config.portal_name||
    (()=>{try{return localStorage.getItem("awg-portal-name")||"";}catch{return "";}})()
    ||"Private World").slice(0,15);
  if(!authed)return(
    <div style={{minHeight:"100vh",background:"var(--bg)",color:"var(--text)",display:"flex",alignItems:"center",justifyContent:"center",fontFamily:"var(--sans)",padding:16}}>
      <style>{GLOBAL_CSS}</style>
      <div style={{width:"100%",maxWidth:400}}>
        {/* До входа — только форма: без названия панели, версии и подставленного логина */}
        <form onSubmit={e=>{e.preventDefault();doLogin();}} autoComplete="off" className="panel"
          style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:"var(--radius-lg)",padding:"24px 24px 28px",display:"flex",flexDirection:"column",gap:16}}>
          <label className="field">
            <span>Логин</span>
            <input type="text" value={lUser} onChange={e=>setLUser(e.target.value)} autoComplete="off" autoFocus
              autoCapitalize="none" spellCheck={false}/>
          </label>
          <label className="field">
            <span>Пароль</span>
            <input type="password" value={lPass} onChange={e=>setLPass(e.target.value)} autoComplete="current-password"
              className={lErr&&!needTotp?"invalid":""}/>
          </label>
          {needTotp&&<label className="field">
            <span>Код 2FA</span>
            <input type="text" inputMode="numeric" autoComplete="one-time-code" autoFocus value={lTotp}
              onChange={e=>setLTotp(e.target.value.replace(/\D/g,"").slice(0,6))} placeholder="000000"
              className={lErr?"invalid":""} style={{fontFamily:"var(--mono)",letterSpacing:".3em",textAlign:"center"}}/>
          </label>}
          {lErr&&<div className="alert alert-error">{lErr}</div>}
          <Btn v="primary" type="submit" disabled={lBusy} style={{width:"100%"}}>{lBusy?"Проверка…":"Войти"}</Btn>
        </form>
      </div>
    </div>
  );

  // Пропсы для SideNav (React.memo вне App)
  const sideNavProps = {
    page, setPage, setSideOpen, T,
    online, active, stats, fmtBytes, fmtGB, doLogout,
    clientsCount: clients.length,
  };

  const PAGE_TITLE={dashboard:"Обзор",clients:"Клиенты",add:"Новый клиент",lists:"Списки",nodes:"Ноды",logs:"Журнал",settings:"Настройки"};
  const PAGE_SUB={dashboard:"клиенты, трафик и нагрузка",clients:"подключения на всех нодах",add:"профиль создаётся на каждой ноде",lists:"сети и приложения для маршрутизации WireSock",nodes:"VPN-серверы под управлением панели",logs:"действия администраторов и состояние клиентов",settings:"панель, безопасность, уведомления и резервные копии"};

  return(
    <div style={{background:"var(--bg)",color:"var(--text)",minHeight:"100vh",display:"flex",fontFamily:"var(--sans)",fontSize:14}}>
      <style>{GLOBAL_CSS}</style>

      {/* Desktop sidebar */}
      <aside className="desktop-sb" style={{
        width:sideCollapsed?56:232,flexShrink:0,
        background:"var(--surface)",borderRight:"1px solid var(--border)",
        flexDirection:"column",position:"sticky",top:0,height:"100vh",overflowY:"auto",overflowX:"hidden"}}>
        <div style={{height:48,display:"flex",alignItems:"center",gap:10,flexShrink:0,
          padding:sideCollapsed?0:"0 8px 0 16px",justifyContent:sideCollapsed?"center":"space-between",
          borderBottom:"1px solid var(--border)"}}>
          {!sideCollapsed&&<button className="crumb" onClick={()=>setPage("dashboard")}
            style={{display:"flex",alignItems:"center",gap:10,minWidth:0,color:"var(--text)",textDecoration:"none"}}>
            <Logo/>
            <span style={{fontSize:14,fontWeight:500,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{portalName}</span>
          </button>}
          <button className="tb-btn" onClick={()=>setSideCollapsed(v=>!v)} title={sideCollapsed?"Раскрыть меню":"Свернуть меню"}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              {sideCollapsed?<polyline points="9 6 15 12 9 18"/>:<polyline points="15 6 9 12 15 18"/>}
            </svg>
          </button>
        </div>
        <SideNav {...sideNavProps} collapsed={sideCollapsed}/>
      </aside>

      {/* Mobile overlay sidebar */}
      {sideOpen&&<>
        <div onClick={()=>setSideOpen(false)} style={{position:"fixed",inset:0,background:"var(--overlay-bg)",zIndex:1000}}/>
        <aside style={{position:"fixed",left:0,top:0,bottom:0,width:260,background:"var(--surface)",borderRight:"1px solid var(--border)",zIndex:1001,display:"flex",flexDirection:"column",overflowY:"auto",animation:"sideIn .2s ease"}}>
          <div style={{height:48,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 8px 0 16px",borderBottom:"1px solid var(--border)",flexShrink:0}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}><Logo/><span style={{fontWeight:500}}>{portalName}</span></div>
            <button className="tb-btn" onClick={()=>setSideOpen(false)} title="Закрыть">✕</button>
          </div>
          <SideNav {...sideNavProps}/>
        </aside>
      </>}

      {/* Main column */}
      <div style={{flex:1,display:"flex",flexDirection:"column",minWidth:0}}>
        <header style={{background:"var(--surface)",borderBottom:"1px solid var(--border)",padding:"0 16px",height:48,display:"flex",alignItems:"center",gap:12,position:"sticky",top:0,zIndex:50,flexShrink:0}}>
          <button className="tb-btn mob-btn" onClick={()=>setSideOpen(true)} title="Меню">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          {/* Хлебные крошки */}
          <nav style={{flex:1,minWidth:0,display:"flex",alignItems:"center",gap:8,fontSize:14,whiteSpace:"nowrap",overflow:"hidden"}}>
            <button className="crumb hide-mob" onClick={()=>setPage("dashboard")}>Главная</button>
            <span className="hide-mob" style={{color:"var(--muted)"}}>›</span>
            <span style={{color:"var(--text)",fontWeight:500,overflow:"hidden",textOverflow:"ellipsis"}}>{PAGE_TITLE[page]||page}</span>
            {config.wg_host&&<span className="crumb-host" style={{marginLeft:8,color:"var(--muted)",fontFamily:"var(--mono)",fontSize:12,overflow:"hidden",textOverflow:"ellipsis"}}>
              {config.wg_host}{config.wg_port?` · UDP ${config.wg_port}`:""}
            </span>}
          </nav>
          {/* Живая сводка */}
          <div className="topbar-strip" style={{display:"flex",alignItems:"center",gap:16,fontSize:12,fontFamily:"var(--mono)",flexShrink:0,userSelect:"none"}}>
            <span title="Клиентов онлайн / всего" style={{display:"flex",alignItems:"center",gap:6,color:"var(--muted)"}}>
              <span style={{width:8,height:8,borderRadius:"50%",background:online>0?"var(--success)":active>0?"var(--warning)":"var(--disabled)"}}/>
              <span style={{color:"var(--text)"}}>{online}</span>/{clients.length}
            </span>
            <span title="Скачивание клиентов" style={{color:"var(--viz-green)",minWidth:92,textAlign:"right"}}>↓ {fmtBits(txSpd)}</span>
            <span title="Отдача клиентов" style={{color:"var(--viz-blue)",minWidth:92,textAlign:"right"}}>↑ {fmtBits(rxSpd)}</span>
          </div>
          <span className="topbar-clock" style={{fontFamily:"var(--mono)",fontSize:12,color:"var(--muted)",flexShrink:0}}>{clock}</span>
          <button className="tb-btn" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")}
            title={theme==="dark"?"Светлая тема":"Тёмная тема"}>{theme==="dark"?SUN:MOON}</button>
        </header>

        {/* Content */}
        <main style={{flex:1,padding:"16px 24px 32px",overflowX:"hidden"}}>
          <div style={{width:"100%",maxWidth:1400,margin:"0 auto"}}>
          {/* Заголовок страницы */}
          <div style={{marginBottom:16}}>
            <h1 style={{fontSize:24,fontWeight:400,lineHeight:1.3,color:"var(--text)"}}>{PAGE_TITLE[page]||page}</h1>
            <div className="page-title-sub" style={{fontSize:14,color:"var(--muted)"}}>{PAGE_SUB[page]||""}</div>
          </div>

          {/* ──────────────────── DASHBOARD ──────────────────── */}
          {page==="dashboard"&&(()=>{
            const now   = Date.now();
            const today = clientUsageStore.dayKey(now);

            // Периоды
            const monthFrom  = clientUsageStore.dayKey(now - 30*86400000);
            const halfYrFrom = clientUsageStore.dayKey(now - 182*86400000);
            const yearFrom   = `${new Date(now + 3*3600000).getUTCFullYear()}-01-01`;

            const top3Month  = clientUsageStore.topN(clientUsage, 3, monthFrom,  today);
            const top3Half   = clientUsageStore.topN(clientUsage, 3, halfYrFrom, today);
            const top3Year   = clientUsageStore.topN(clientUsage, 3, yearFrom,   today);

            // Аналитика: распределение трафика по клиентам (текущие значения из wg-easy)
            const totalBytes = clients.reduce((s,c)=>s+(c.tx||0)+(c.rx||0),0);
            const pieData = clients
              .map(c=>({name:c.name, bytes:(c.tx||0)+(c.rx||0), color:aColor(c.name)}))
              .filter(x=>x.bytes>0)
              .sort((a,b)=>b.bytes-a.bytes)
              .slice(0,8);

            // Топ клиентов за период — панель с горизонтальными столбцами (bar gauge)
            const TopBox = ({title, period, data, accent}) => (
              <Card style={{flex:"1 1 260px",minWidth:0}}>
                <CardH sub={period}>{title}</CardH>
                <div className="top3-box" style={{padding:"8px 16px 12px"}}>
                {data.length===0
                  ? <div style={{fontSize:14,color:"var(--muted)",padding:"8px 0"}}>Нет данных — накапливаются автоматически</div>
                  : data.map((item,i)=>(
                  <div key={item.id} style={{padding:"6px 0"}}>
                    <div style={{display:"flex",alignItems:"baseline",gap:8,fontSize:14}}>
                      <span style={{color:"var(--muted)",fontFamily:"var(--mono)",fontSize:12,width:14}}>{i+1}</span>
                      <span style={{flex:1,minWidth:0,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{item.name}</span>
                      <span style={{fontFamily:"var(--mono)",fontSize:12,color:accent,flexShrink:0}}>{fmtBytes(item.bytes)}</span>
                    </div>
                    <div style={{marginTop:4,marginLeft:22,height:6,background:"var(--wmd-bar)",borderRadius:"var(--radius)",overflow:"hidden"}}>
                      <div style={{height:"100%",background:accent,width:`${Math.round((item.bytes/Math.max(data[0].bytes,1))*100)}%`}}/>
                    </div>
                  </div>
                ))}
                </div>
              </Card>
            );

            return(<div style={{display:"flex",flexDirection:"column",gap:16,width:"100%"}}>

              <div className="top3-grid" style={{display:"flex",gap:16,flexWrap:"wrap"}}>
                <TopBox title="Топ месяца"    period="последние 30 дней"    data={top3Month}  accent="var(--viz-blue)"/>
                <TopBox title="Топ полугодия" period="последние 6 месяцев"  data={top3Half}   accent="var(--viz-purple)"/>
                <TopBox title="Топ года"      period={`с 1 января ${new Date(now+3*3600000).getUTCFullYear()}`} data={top3Year} accent="var(--viz-orange)"/>
              </div>

              <Card>
                <CardH right={<div className="radio-group">
                  {["1h","24h","7d","30d"].map(p=>(
                    <button key={p} onClick={()=>setTrafficPeriod(p)} className={trafficPeriod===p?"on":""}>{p}</button>
                  ))}
                </div>}>Трафик</CardH>
                <TrafficChart points={trafficPts} period={trafficPeriod} txSpd={txSpd} rxSpd={rxSpd} rxColor="#73bf69" txColor="#5794f2"/>
              </Card>

              {/* ── Два блока аналитики ── */}
              <div style={{display:"flex",gap:12,flexWrap:"wrap"}}>

                {/* Donut: распределение трафика */}
                <Card style={{flex:"1 1 320px",minWidth:300}}>
                  <CardH>Распределение трафика</CardH>
                  <div style={{padding:"16px 20px",display:"flex",gap:20,alignItems:"center"}}>
                    {pieData.length===0
                      ? <div style={{fontSize:14,color:"var(--muted)",opacity:.5}}>Нет данных</div>
                      : (<>
                        {/* SVG donut */}
                        <svg width="110" height="110" viewBox="0 0 110 110" style={{flexShrink:0}}>
                          {(()=>{
                            const r=42, cx=55, cy=55, stroke=16;
                            const circ=2*Math.PI*r;
                            let offset=0;
                            return pieData.map((item,i)=>{
                              const pct=item.bytes/totalBytes;
                              const len=pct*circ;
                              const el=(
                                <circle key={i} cx={cx} cy={cy} r={r}
                                  fill="none" stroke={item.color}
                                  strokeWidth={stroke}
                                  strokeDasharray={`${len} ${circ-len}`}
                                  strokeDashoffset={-offset+circ/4}
                                  style={{transition:"stroke-dasharray .4s"}}/>
                              );
                              offset+=len;
                              return el;
                            });
                          })()}
                          <text x="55" y="51" textAnchor="middle" fill="var(--text)"
                            style={{fontSize:"12px",fontWeight:700,fontFamily:"var(--mono)"}}>{pieData.length}</text>
                          <text x="55" y="64" textAnchor="middle" fill="var(--muted)"
                            style={{fontSize:"10px",fontFamily:"var(--sans)"}}>клиент.</text>
                        </svg>
                        {/* Legend */}
                        <div style={{flex:1,display:"flex",flexDirection:"column",gap:5,minWidth:0}}>
                          {pieData.map(item=>(
                            <div key={item.name} style={{display:"flex",alignItems:"center",gap:7,minWidth:0}}>
                              <span style={{width:8,height:8,borderRadius:"var(--radius)",background:item.color,flexShrink:0}}/>
                              <span style={{fontSize:12,color:"var(--text)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",flex:1}}>{item.name}</span>
                              <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)",flexShrink:0}}>
                                {Math.round((item.bytes/totalBytes)*100)}%
                              </span>
                            </div>
                          ))}
                        </div>
                      </>)}
                  </div>
                </Card>

                {/* Онлайн/активность */}
                <Card style={{flex:"1 1 320px",minWidth:300}}>
                  <CardH>Статус клиентов</CardH>
                  <div style={{padding:"16px 20px",display:"flex",flexDirection:"column",gap:12}}>
                    {(()=>{
                      const onlineN  = clients.filter(c=>c.enabled&&c.handshakeAt&&(Date.now()-new Date(c.handshakeAt))<ONLINE_MS).length;
                      const idleN    = clients.filter(c=>c.enabled&&!(c.handshakeAt&&(Date.now()-new Date(c.handshakeAt))<ONLINE_MS)).length;
                      const offN     = clients.filter(c=>!c.enabled).length;
                      const total    = clients.length || 1;
                      const bars = [
                        {label:"Онлайн",  n:onlineN, color:"var(--success)"},
                        {label:"Ожидают",    n:idleN,   color:T.amber},
                        {label:"Выключены", n:offN,    color:"var(--muted)"},
                      ];
                      return bars.map(b=>(
                        <div key={b.label}>
                          <div style={{display:"flex",justifyContent:"space-between",marginBottom:5,fontSize:12}}>
                            <span style={{color:"var(--text)",fontWeight:600}}>{b.label}</span>
                            <span style={{color:b.color,fontFamily:"var(--mono)",fontWeight:700}}>{b.n} / {clients.length}</span>
                          </div>
                          <div style={{height:6,background:"var(--surface2)",borderRadius:"var(--radius)",overflow:"hidden"}}>
                            <div style={{height:"100%",borderRadius:"var(--radius)",background:b.color,
                              width:`${Math.round(b.n/total*100)}%`,transition:"width .4s"}}/>
                          </div>
                        </div>
                      ));
                    })()}
                    <div style={{marginTop:4,paddingTop:12,borderTop:"1px solid var(--border)",
                      display:"flex",gap:16,fontSize:12}}>
                      <div>
                        <div style={{color:"var(--muted)",fontSize:12,marginBottom:2}}>Отдано</div>
                        <div style={{color:T.amber,fontFamily:"var(--mono)",fontWeight:700}}>
                          {fmtBytes(clients.reduce((s,c)=>s+(c.tx||0),0))}
                        </div>
                      </div>
                      <div>
                        <div style={{color:"var(--muted)",fontSize:12,marginBottom:2}}>Получено</div>
                        <div style={{color:"var(--success)",fontFamily:"var(--mono)",fontWeight:700}}>
                          {fmtBytes(clients.reduce((s,c)=>s+(c.rx||0),0))}
                        </div>
                      </div>
                      <div>
                        <div style={{color:"var(--muted)",fontSize:12,marginBottom:2}}>С лимитом</div>
                        <div style={{color:T.cyan,fontFamily:"var(--mono)",fontWeight:700}}>
                          {Object.keys(limits).length} / {clients.length}
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>

              </div>
            </div>);
          })()}

          {/* ──────────────────── CLIENTS ──────────────────── */}
          {page==="clients"&&(()=>{
            const now = Date.now();
            const monthFrom = clientUsageStore.dayKey(now - 30*86400000);
            const monthTo   = clientUsageStore.dayKey(now);
            const visible=clients.filter(c=>{
              const m=clientMeta[c.id]||{};
              const q=searchQ.toLowerCase();
              return(!q||c.name.toLowerCase().includes(q)||(c.ip||"").includes(q)||(m.note||"").toLowerCase().includes(q)
                ||(c.uid&&q.length>2&&c.uid.startsWith(q.replace(/^#/,""))))&&(filterGroup==="all"||(m.group||"Без группы")===filterGroup);
            });
            // Одинаковые имена разрешены — у таких клиентов ID показывается рядом с именем
            const nameCount={}; clients.forEach(c=>{const k=(c.name||"").toLowerCase(); nameCount[k]=(nameCount[k]||0)+1;});
            return(<div style={{display:"flex",flexDirection:"column",gap:16,width:"100%"}}>
              {/* Toolbar */}
              <div className="clients-toolbar" style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
                <div style={{position:"relative",flex:"1 1 200px",maxWidth:320}}>
                  <svg style={{position:"absolute",left:8,top:"50%",transform:"translateY(-50%)",color:"var(--muted)",pointerEvents:"none"}} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/></svg>
                  <input value={searchQ} onChange={e=>setSearchQ(e.target.value)} placeholder="Поиск по имени, IP, заметке или #ID" style={{width:"100%",paddingLeft:30,display:"block"}}/>
                </div>
                <div className="radio-group" style={{flexWrap:"wrap"}}>
                  {["all",...GROUPS].map(g=>{
                    const cnt=g==="all"?clients.length:clients.filter(c=>(clientMeta[c.id]?.group||"Без группы")===g).length;
                    return(<button key={g} onClick={()=>setFilterGroup(g)} className={filterGroup===g?"on":""} style={{height:30,display:"inline-flex",alignItems:"center",gap:6}}>
                      {g!=="all"&&<span style={{width:8,height:8,borderRadius:"50%",background:GC[g]||"var(--disabled)"}}/>}
                      {g==="all"?"Все":g}<span style={{fontFamily:"var(--mono)",color:"var(--muted)"}}>{cnt}</span>
                    </button>);
                  })}
                </div>
                <span style={{flex:1}}/>
                <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>{visible.length} из {clients.length}</span>
                <Btn v="icon" onClick={loadClients} disabled={cBusy} title="Обновить">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/></svg>
                </Btn>
                <Btn v="primary" onClick={()=>setPage("add")}>Новый клиент</Btn>
              </div>

              {cErr&&<div className="alert alert-error">{cErr}</div>}

              <Card>
                {/* Table header — desktop only */}
                <div className="hide-mob th" style={{display:"grid",gridTemplateColumns:"24px 28px 84px minmax(150px,1.6fr) 96px 80px 80px 80px 80px 72px 84px 156px",padding:"8px 12px",borderBottom:"1px solid var(--border)",gap:6,alignItems:"center"}}>
                  <span style={{textAlign:"center"}}>#</span><span/>
                  <span>Статус</span>
                  <span>Клиент</span><span>IP</span>
                  <span>Отдано</span><span>Получено</span>
                  <span>Всего</span>
                  <span>За месяц</span>
                  <span>Создан</span>
                  <span>Лимит</span>
                  <span style={{textAlign:"right"}}>Действия</span>
                </div>

                {cBusy&&<div style={{display:"flex",alignItems:"center",gap:10,padding:"24px 16px",color:"var(--muted)",fontSize:14}}><div style={{width:14,height:14,border:"2px solid var(--border-medium)",borderTopColor:"var(--primary)",borderRadius:"50%",animation:"spin .7s linear infinite"}}/>Загрузка…</div>}
                {!cBusy&&visible.length===0&&<div style={{padding:"48px 16px",textAlign:"center"}}><div style={{fontSize:16,marginBottom:8}}>{clients.length===0?"Клиентов пока нет":"Ничего не найдено"}</div>{clients.length===0&&<><div style={{fontSize:14,color:"var(--muted)",marginBottom:16}}>Профиль клиента создаётся сразу на всех нодах</div><Btn v="primary" onClick={()=>setPage("add")}>Создать клиента</Btn></>}</div>}

                {!cBusy&&visible.map((c,idx)=>{
                  const ip=(c.ip||"").replace("/32","");
                  const on=c.enabled&&c.handshakeAt&&(Date.now()-new Date(c.handshakeAt))<ONLINE_MS;
                  const m=clientMeta[c.id]||{};
                  const grpC=GC[m.group||"Без группы"]||"var(--muted)";
                  const rt=routingAll[c.id];
                  const MODE={include:"только списки",exclude:"кроме списков"};
                  const routed=rt&&(rt.net_mode!=="all"||rt.app_mode!=="all"||rt.custom)
                    ?[`сети: ${MODE[rt.net_mode]||"все"}`,`приложения: ${MODE[rt.app_mode]||"все"}`,rt.custom?"свои параметры":null].filter(Boolean).join(" · "):null;
                  const expired=m.expiresAt&&new Date(m.expiresAt)<new Date();
                  const expWarn=!expired&&m.expiresAt&&Math.ceil((new Date(m.expiresAt)-Date.now())/86400000)<7;
                  const lim=c.limit;
                  const days=m.expiresAt?Math.ceil((new Date(m.expiresAt)-Date.now())/86400000):null;
                  const stC=on?"var(--success)":c.enabled?"var(--warning)":"var(--disabled)";
                  return(<div key={c.id} className="rh" style={{borderBottom:"1px solid var(--border)"}}>
                    {/* Desktop row */}
                    <div className="hide-mob" style={{display:"grid",gridTemplateColumns:"24px 28px 84px minmax(150px,1.6fr) 96px 80px 80px 80px 80px 72px 84px 156px",padding:"6px 12px",minHeight:44,alignItems:"center",gap:6,fontSize:14}}>
                      <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)",textAlign:"center"}}>{idx+1}</span>
                      <div style={{width:24,height:24,borderRadius:"50%",background:aColor(c.name),display:"flex",alignItems:"center",justifyContent:"center",fontSize:12,fontWeight:500,color:"#fff"}}>{(c.name||"?").charAt(0).toUpperCase()}</div>
                      <span style={{display:"inline-flex",alignItems:"center",gap:6,fontSize:12,color:stC}}>
                        <span style={{width:8,height:8,borderRadius:"50%",background:stC,flexShrink:0}}/>
                        {on?"Онлайн":c.enabled?"Ожидает":"Выключен"}
                      </span>
                      <div style={{minWidth:0}}>
                        <div style={{display:"flex",alignItems:"center",gap:4,overflow:"hidden"}}>
                          <span style={{fontWeight:500,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{c.name}</span>
                          {m.group&&m.group!=="Без группы"&&<span style={tag(grpC)}>{m.group}</span>}
                          {routed&&<span title={routed} style={tag("var(--cyan)")}>WS</span>}
                          {(c.nodes||[]).length>1&&<span title={"Профили на нодах:\n"+c.nodes.map(n=>`${n.handshakeAt&&(Date.now()-new Date(n.handshakeAt))<ONLINE_MS?"● ":"○ "}${n.name}`).join("\n")} style={tag("var(--muted)")}>{c.nodes.length} ноды</span>}
                          {(c.nodes||[]).length===0&&<span title="Профили создаются на нодах — подождите синхронизации" style={tag("var(--warning)")}>нет нод</span>}
                          {expired&&<span style={tag("var(--error)")}>истёк</span>}
                          {!expired&&days!=null&&<span title={`Доступ до ${new Date(m.expiresAt).toLocaleDateString("ru")}`} style={tag(days<3?"var(--error)":days<7?"var(--warning)":"var(--success)")}>{days} д</span>}
                        </div>
                        {(m.note||nameCount[(c.name||"").toLowerCase()]>1)&&<div style={{fontSize:12,color:"var(--muted)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                          {nameCount[(c.name||"").toLowerCase()]>1&&c.uid&&<span title="ID клиента — различает одинаковые имена" style={{fontFamily:"var(--mono)",marginRight:6,color:"var(--cyan)"}}>#{c.uid}</span>}
                          {m.note}
                        </div>}
                      </div>
                      <span style={{fontFamily:"var(--mono)",fontSize:12}}>{ip}</span>
                      <span style={{fontFamily:"var(--mono)",fontSize:12,color:"var(--muted)"}}>{fmtBytes(c.tx||0)}</span>
                      <span style={{fontFamily:"var(--mono)",fontSize:12,color:"var(--muted)"}}>{fmtBytes(c.rx||0)}</span>
                      <span style={{fontFamily:"var(--mono)",fontSize:12}}>{fmtGB((c.tx||0)+(c.rx||0))}</span>
                      <span style={{fontFamily:"var(--mono)",fontSize:12}}>
                        {(()=>{const b=clientUsageStore.sumForClient(clientUsage,c.id,monthFrom,monthTo);return b>0?fmtBytes(b):"—";})()}
                      </span>
                      <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>
                        {m.createdAt ? new Date(m.createdAt).toLocaleDateString("ru",{day:"2-digit",month:"2-digit",year:"2-digit",timeZone:getPanelTz()}) : "—"}
                      </span>
                      <button className="crumb" onClick={()=>setEditLimit({id:c.id,ip:c.ip,down:lim?.down??5,up:lim?.up??5,hasLimit:!!lim})} title="Лимит скорости"
                        style={{textAlign:"left",fontSize:12,fontFamily:"var(--mono)",lineHeight:1.4,color:lim?"var(--text)":"var(--muted)"}}>
                        {lim?<>↓{lim.down}M<br/>↑{lim.up}M</>:"без лимита"}
                      </button>
                      <div style={{display:"flex",gap:4,justifyContent:"flex-end"}}>
                        <Btn v="icon" onClick={()=>setQrClient(c)} title="Конфиг и QR-код" style={{width:28,height:28}}>{IC.qr}</Btn>
                        <Btn v="icon" onClick={()=>setEditMeta(c)} title="Редактировать" style={{width:28,height:28}}>{IC.edit}</Btn>
                        <Btn v="icon" onClick={()=>setEditRouting(c)} title="Маршрутизация (WireSock)" style={{width:28,height:28}}>{IC.route}</Btn>
                        <Btn v="icon" onClick={()=>toggleClient(c)} title={c.enabled?"Отключить":"Включить"} style={{width:28,height:28}}>{c.enabled?IC.pause:IC.play}</Btn>
                        <Btn v="danger" onClick={()=>delClient(c)} title="Удалить" style={{width:28,height:28,padding:0}}>{IC.trash}</Btn>
                      </div>
                    </div>

                    {/* Mobile card */}
                    <div className="mob-btn" style={{display:"none",padding:"12px 16px",flexDirection:"column",gap:8}}>
                      <div style={{display:"flex",alignItems:"center",gap:10}}>
                        <div style={{width:32,height:32,borderRadius:"50%",background:aColor(c.name),display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,fontWeight:500,color:"#fff",flexShrink:0}}>{(c.name||"?").charAt(0).toUpperCase()}</div>
                        <div style={{flex:1,minWidth:0}}>
                          <div style={{fontWeight:500,fontSize:14,display:"flex",alignItems:"center",gap:6,flexWrap:"wrap"}}>
                            {c.name}
                            {m.group&&m.group!=="Без группы"&&<span style={tag(grpC)}>{m.group}</span>}
                            {expired&&<span style={tag("var(--error)")}>истёк</span>}
                          </div>
                          <div style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>{ip}</div>
                        </div>
                        <span style={{display:"inline-flex",alignItems:"center",gap:6,fontSize:12,color:stC}}>
                          <span style={{width:8,height:8,borderRadius:"50%",background:stC}}/>{on?"Онлайн":c.enabled?"Ожидает":"Выключен"}
                        </span>
                      </div>
                      <div style={{display:"flex",gap:12,fontSize:12,fontFamily:"var(--mono)",color:"var(--muted)",flexWrap:"wrap"}}>
                        <span>↑ {fmtBytes(c.tx||0)}</span>
                        <span>↓ {fmtBytes(c.rx||0)}</span>
                        <span style={{color:"var(--text)"}}>Σ {fmtGB((c.tx||0)+(c.rx||0))}</span>
                        {lim&&<span>лимит ↓{lim.down} ↑{lim.up} Мбит/с</span>}
                      </div>
                      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                        <Btn v="primary" onClick={()=>setQrClient(c)} style={{flex:1}}>Конфиг</Btn>
                        <Btn v="icon" onClick={()=>setEditMeta(c)} title="Редактировать">{IC.edit}</Btn>
                        <Btn v="icon" onClick={()=>setEditRouting(c)} title="Маршрутизация">{IC.route}</Btn>
                        <Btn v="icon" onClick={()=>setEditLimit({id:c.id,ip:c.ip,down:lim?.down??5,up:lim?.up??5,hasLimit:!!lim})} title="Лимит скорости">{IC.gauge}</Btn>
                        <Btn v="icon" onClick={()=>toggleClient(c)} title={c.enabled?"Отключить":"Включить"}>{c.enabled?IC.pause:IC.play}</Btn>
                        <Btn v="danger" onClick={()=>delClient(c)} title="Удалить" style={{width:32,padding:0}}>{IC.trash}</Btn>
                      </div>
                    </div>
                  </div>);
                })}
              </Card>
            </div>);
          })()}

          {/* ──────────────────── ADD ──────────────────── */}
          {page==="add"&&<div className="page-form" style={{display:"flex",justifyContent:"center",width:"100%"}}><AddClientPage push={push} setQrClient={setQrClient} setPage={setPage} clients={clients} onCreated={c=>setClients(cs=>[...cs.filter(x=>x.id!==c.id),c])}/></div>}

          {/* ──────────────────── LISTS ──────────────────── */}
          {page==="lists"&&<ListsPage push={push} setConfirmModal={setConfirmModal} onChanged={loadRouting}/>}
          {page==="nodes"&&<NodesPage push={push} setConfirmModal={setConfirmModal}/>}

          {/* ──────────────────── SETTINGS ──────────────────── */}
          {page==="settings"&&(<div className="wide-page" style={{width:"100%",maxWidth:780,display:"flex",flexDirection:"column",gap:14,margin:"0 auto"}}>

            {/* ── Название панели ── */}
            <PortalNameCard config={config} setConfig={setConfig} push={push}/>
            <SecurityCard push={push}/>
            <TimezoneCard config={config} setConfig={setConfig} push={push}/>
            <GroupsCard push={push} setConfirmModal={setConfirmModal} onChanged={loadClients}/>
            {/* ── Сброс трафика ── */}
            <ResetTrafficCard T={T} push={push} setTrafficPts={setTrafficPts} setClientUsage={setClientUsage}/>
            <Card>
              <CardH sub="применяется на ноде сразу после сохранения">Лимиты скорости</CardH>
              <div style={{padding:"12px 18px"}}>
                {Object.keys(limits).length===0
                  ?<div style={{fontSize:14,color:"var(--muted)",padding:"4px 0",lineHeight:1.7}}>Лимиты не установлены. Задаются в колонке «Лимит» на странице «Клиенты».</div>
                  :<div>{clients.filter(c=>c.limit).map(c=>{const ip=c.ip,cfg=c.limit;return(<div key={c.id} style={{display:"flex",alignItems:"center",gap:10,padding:"8px 0",borderBottom:`1px solid ${T.border}`,fontSize:14}}>
                    <span style={{fontFamily:"var(--mono)",color:T.cyan,flex:1}}>{ip}</span>
                    <span style={{color:T.amber,fontFamily:"var(--mono)"}}>↓{cfg.down}M</span>
                    <span style={{color:"var(--muted)",fontFamily:"var(--mono)"}}>↑{cfg.up}M</span>
                    <span style={{color:"var(--muted)"}}>{c.name}</span>
                    <button onClick={()=>removeLimit(c.id)} title="Снять лимит" style={{background:"none",border:"none",color:"var(--error)",cursor:"pointer",fontSize:16,padding:"0 4px"}}>✕</button>
                  </div>);})}</div>}
              </div>
            </Card>
            <TelegramCard push={push}/>
            <BotCard push={push}/>
            <UserPageCard push={push}/>
            <BackupCard push={push} setConfirmModal={setConfirmModal}/>
          </div>)}

          {/* ──────────────────── LOGS ──────────────────── */}
          {page==="logs"&&(()=>{
            // ── Журнал событий — собираем живые данные ──────────────
            const logClients = [...clients].sort((a,b)=>{
              const ta = a.handshakeAt ? new Date(a.handshakeAt).getTime() : 0;
              const tb = b.handshakeAt ? new Date(b.handshakeAt).getTime() : 0;
              return tb - ta;
            });
            const now = Date.now();
            const onlineList  = logClients.filter(c=>c.enabled&&c.handshakeAt&&(now-new Date(c.handshakeAt))<ONLINE_MS);
            const recentList  = logClients.filter(c=>c.handshakeAt&&(now-new Date(c.handshakeAt))<3600000&&!onlineList.includes(c));
            const expiredList = logClients.filter(c=>{ const m=clientMeta[c.id]||{}; return m.expiresAt&&new Date(m.expiresAt)<new Date(); });
            const noLimitList = logClients.filter(c=>{ const ip=c.ip; return c.enabled&&ip&&!c.limit; });
            const LEVEL_CFG = {
              OK:   {bg:"color-mix(in srgb,var(--success) 10%,transparent)",  border:"color-mix(in srgb,var(--success) 25%,transparent)",  text:"var(--success)",  dot:"var(--success)"},
              INFO: {bg:`color-mix(in srgb,var(--cyan) 8%,transparent)`, border:`color-mix(in srgb,var(--cyan) 20%,transparent)`,  text:T.cyan,     dot:T.cyan},
              WARN: {bg:"color-mix(in srgb,var(--warning) 8%,transparent)", border:"color-mix(in srgb,var(--warning) 20%,transparent)",  text:T.amber,    dot:T.amber},
              ERR:  {bg:"color-mix(in srgb,var(--error) 10%,transparent)", border:"color-mix(in srgb,var(--error) 25%,transparent)",text:"var(--error)",  dot:"var(--error)"},
            };
            const Row=({level,time,msg,sub})=>{
              const lc = LEVEL_CFG[level]||LEVEL_CFG.INFO;
              return (
                <div style={{display:"flex",gap:12,padding:"9px 0",borderBottom:"1px solid rgba(255,255,255,.035)",alignItems:"flex-start"}}>
                  {/* Badge */}
                  <div style={{flexShrink:0,marginTop:1}}>
                    <span style={{display:"inline-flex",alignItems:"center",gap:4,
                      padding:"2px 7px",borderRadius:"var(--radius)",fontSize:11,fontWeight:700,
                      fontFamily:"var(--mono)",
                      background:lc.bg,border:`1px solid ${lc.border}`,color:lc.text}}>
                      <span style={{width:5,height:5,borderRadius:"50%",background:lc.dot,flexShrink:0}}/>
                      {level}
                    </span>
                  </div>
                  {/* Content */}
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{display:"flex",alignItems:"baseline",gap:10,flexWrap:"wrap"}}>
                      <span style={{fontSize:14,color:"var(--text)",lineHeight:1.5,fontWeight:500}}>{msg}</span>
                      {time&&<span style={{fontSize:12,color:"var(--muted)",flexShrink:0,fontFamily:"var(--mono)",opacity:.7}}>{time}</span>}
                    </div>
                    {sub&&<div style={{fontSize:12,color:"var(--muted)",marginTop:3,lineHeight:1.6,fontFamily:"var(--mono)",opacity:.8}}>{sub}</div>}
                  </div>
                </div>
              );
            };
            const fmtAgo=(ts)=>{ if(!ts)return"—"; const s=Math.floor((now-new Date(ts))/1000); if(s<60)return s+"с назад"; if(s<3600)return Math.floor(s/60)+"м назад"; if(s<86400)return Math.floor(s/3600)+"ч назад"; return Math.floor(s/86400)+"д назад"; };
            return(<div style={{width:"100%",display:"flex",flexDirection:"column",gap:14}}>

              <AuditLog/>

              {/* ── Сводка системы ── */}
              <Card>
                <CardH sub="текущее состояние системы">Системные метрики</CardH>
                <div style={{padding:"8px 18px 12px"}}>
                  {[
                    stats&&{level:"OK", msg:`CPU ${Math.round(stats.cpu)}%  ·  RAM ${Math.round(stats.ram_pct)}% (${fmtGB(stats.ram_used)})  ·  Диск ${Math.round(stats.disk_pct)}% (${fmtGB(stats.disk_used)} / ${fmtGB(stats.disk_total)})`, sub:`Load avg: ${stats.load1}`},
                    {level:"INFO", msg:`Клиентов: ${clients.length}  ·  активных: ${active}  ·  онлайн: ${online}`, sub:`TX всего: ${fmtBytes(totalTx)}  ·  RX всего: ${fmtBytes(totalRx)}`},
                    config.wg_host&&{level:"INFO", msg:`${config.wg_port?`WireGuard: ${config.wg_host}:${config.wg_port}/udp  ·  `:""}Web UI: ${config.wg_host}:${config.web_port}`, sub:`Tunnelwright Panel AWG v${APP_VERSION}`},
                    tg&&(tg.active
                      ?{level:"OK", msg:"Telegram уведомления активны",
                        sub:`Chat ID: ${tg.chat_id}  ·  Событий: ${Object.values(tg.events||{}).filter(Boolean).length}`}
                      :(tg.token_set
                        ?{level:"WARN", msg:"Telegram настроен но отключён", sub:"Включите уведомления в разделе Настройки"}
                        :{level:"WARN", msg:"Telegram не настроен", sub:"Добавьте бота в разделе Настройки → Telegram"})),
                    {level:Object.keys(limits).length>0?"OK":"WARN", msg:`Лимиты скорости: ${Object.keys(limits).length} клиент(ов)`, sub:Object.keys(limits).length>0?Object.entries(limits).slice(0,3).map(([ip,l])=>`${ip}: ↓${l.down}M ↑${l.up}M`).join("  ·  ")+(Object.keys(limits).length>3?`  +${Object.keys(limits).length-3} ещё`:""):"Лимиты не установлены"},
                  ].filter(Boolean).map((r,i)=><Row key={i} {...r}/>)}
                </div>
              </Card>

              {/* ── Онлайн прямо сейчас ── */}
              {onlineList.length>0&&<Card>
                <CardH sub={`${onlineList.length} клиент(ов) активны прямо сейчас`}>Online сейчас</CardH>
                <div style={{padding:"8px 18px 12px"}}>
                  {onlineList.map(c=>{
                    const ip=c.ip;
                    const m=clientMeta[c.id]||{};
                    return <Row key={c.id} level="OK"
                      msg={`${c.name}  ·  ${ip}`}
                      sub={`Хендшейк: ${fmtAgo(c.handshakeAt)}  ·  TX: ${fmtBytes(c.tx||0)}  ·  RX: ${fmtBytes(c.rx||0)}${m.group&&m.group!=="Без группы"?" · "+m.group:""}`}/>;
                  })}
                </div>
              </Card>}

              {/* ── Недавно были онлайн ── */}
              {recentList.length>0&&<Card>
                <CardH sub="были онлайн в последний час">Недавно активны</CardH>
                <div style={{padding:"8px 18px 12px"}}>
                  {recentList.slice(0,8).map(c=>{
                    const ip=c.ip;
                    return <Row key={c.id} level="INFO"
                      msg={`${c.name}  ·  ${ip}`}
                      sub={`Последний сеанс: ${fmtAgo(c.handshakeAt)}  ·  TX: ${fmtBytes(c.tx||0)}  ·  RX: ${fmtBytes(c.rx||0)}`}/>;
                  })}
                </div>
              </Card>}

              {/* ── Предупреждения ── */}
              {(expiredList.length>0||noLimitList.length>0)&&<Card>
                <CardH sub="требуют внимания">Предупреждения</CardH>
                <div style={{padding:"8px 18px 12px"}}>
                  {expiredList.map(c=><Row key={"exp-"+c.id} level="WARN"
                    msg={`Срок доступа истёк: ${c.name}`}
                    sub={`IP: ${c.ip}  ·  Истёк: ${new Date(clientMeta[c.id]?.expiresAt).toLocaleDateString("ru")}`}/>)}
                  {noLimitList.map(c=><Row key={"nl-"+c.id} level="WARN"
                    msg={`Без лимита скорости: ${c.name}`}
                    sub={`IP: ${c.ip}  ·  Трафик не ограничен`}/>)}
                </div>
              </Card>}

              {/* ── Все клиенты — сортировка по активности ── */}
              <Card>
                <CardH sub="сортировка по последнему хендшейку">Все клиенты</CardH>
                <div style={{padding:"8px 18px 12px"}}>
                  {logClients.map(c=>{
                    const ip=c.ip;
                    const m=clientMeta[c.id]||{};
                    const lim=c.limit;
                    const isOnline=c.enabled&&c.handshakeAt&&(now-new Date(c.handshakeAt))<ONLINE_MS;
                    const level=!c.enabled?"WARN":isOnline?"OK":"INFO";
                    return <Row key={c.id} level={level}
                      msg={`${c.name}  ·  ${ip}${!c.enabled?" · [отключён]":""}`}
                      sub={[
                        c.handshakeAt?`Последний сеанс: ${fmtAgo(c.handshakeAt)}`:"Никогда не подключался",
                        `TX: ${fmtBytes(c.tx||0)}  RX: ${fmtBytes(c.rx||0)}`,
                        lim?`Лимит: ↓${lim.down}M ↑${lim.up}M`:"Без лимита",
                        m.group&&m.group!=="Без группы"?`Группа: ${m.group}`:null,
                      ].filter(Boolean).join("  ·  ")}/>;
                  })}
                </div>
              </Card>

            </div>);
          })()}

          </div>{/* /maxWidth */}
        </main>
      </div>

      {/* Modals */}
      {qrClient&&<QRModal client={qrClient} onClose={()=>setQrClient(null)}/>}
      {editLimit&&<LimitModal data={editLimit} onSave={(_ip,d,u)=>updateLimit(editLimit.id,d,u)} onRemove={()=>removeLimit(editLimit.id)} onClose={()=>setEditLimit(null)}/>}
      {editMeta&&<MetaModal client={editMeta} meta={clientMeta[editMeta.id]||{}} allClients={clients} onSave={(p)=>saveMeta(editMeta.id,p)} onClose={()=>setEditMeta(null)}/>}
      {editRouting&&<RoutingModal client={editRouting} push={push} setPage={setPage} onSaved={loadRouting} onClose={()=>setEditRouting(null)}/>}
      {confirmModal&&<ConfirmModal title={confirmModal.title} detail={confirmModal.detail} confirmLabel={confirmModal.confirmLabel} onConfirm={confirmModal.onConfirm} onClose={()=>setConfirmModal(null)}/>}
      <Stack/>

    </div>
  );
}

export default App;
