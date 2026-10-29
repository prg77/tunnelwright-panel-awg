import React, { useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

const inputStyle = {flex:1,minWidth:160,background:"var(--bg)",border:"1px solid var(--border)",
  borderRadius:"var(--radius)",color:"var(--text)",fontSize:14,padding:"8px 12px"};
const codeStyle = {...inputStyle, flex:"0 0 130px", minWidth:0, fontFamily:"var(--mono)",
  letterSpacing:".3em", textAlign:"center"};

// ─── SecurityCard — пароль администратора и 2FA (TOTP) ──────────
export const SecurityCard = ({ push }) => {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState(null);
  const [setup, setSetup] = useState(null);       // {secret, qr_svg} — в процессе включения 2FA
  const [code, setCode] = useState("");
  const [offPass, setOffPass] = useState("");

  React.useEffect(() => { api.session().then(setSession).catch(() => {}); }, []);
  const err = (e) => push({type:"err", title:"Ошибка", detail:e.message});

  const changePassword = async () => {
    setBusy(true);
    try {
      await api.changePassword(cur, next);
      setCur(""); setNext("");
      push({type:"ok", title:"Пароль изменён", detail:"Другие сессии завершены"});
    } catch (e) { err(e); } finally { setBusy(false); }
  };
  const startTotp = async () => {
    try { setSetup(await api.totpSetup()); setCode(""); } catch (e) { err(e); }
  };
  const enableTotp = async () => {
    try {
      await api.totpEnable(code);
      setSetup(null); setCode("");
      setSession(s => ({...s, totp_enabled:true}));
      push({type:"ok", title:"2FA включена", detail:"При входе понадобится код из приложения"});
    } catch (e) { err(e); }
  };
  const disableTotp = async () => {
    try {
      await api.totpDisable(code, offPass);
      setCode(""); setOffPass("");
      setSession(s => ({...s, totp_enabled:false}));
      push({type:"warn", title:"2FA отключена"});
    } catch (e) { err(e); }
  };

  return (
    <Card>
      <CardH sub={session ? `вход: ${session.username}` : ""}>Безопасность</CardH>
      <div style={{padding:"12px 18px",display:"flex",flexDirection:"column",gap:14}}>
        <div style={{fontSize:14,fontWeight:600}}>Пароль администратора</div>
        <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
          <input type="password" autoComplete="current-password" placeholder="Текущий пароль"
            value={cur} onChange={e=>setCur(e.target.value)} style={inputStyle}/>
          <input type="password" autoComplete="new-password" placeholder="Новый пароль (от 8 символов)"
            value={next} onChange={e=>setNext(e.target.value)} style={inputStyle}/>
          <Btn v="primary" disabled={busy||!cur||next.length<8} onClick={changePassword}>Сменить</Btn>
        </div>

        <div style={{height:1,background:"var(--border)"}}/>
        <div style={{fontSize:14,fontWeight:600}}>
          Двухфакторная аутентификация (2FA) · {session?.totp_enabled
            ? <span style={{color:"var(--success)"}}>включена</span>
            : <span style={{color:"var(--muted)"}}>выключена</span>}
        </div>

        {!session?.totp_enabled && !setup && (
          <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
            <span style={{fontSize:12,color:"var(--muted)",flex:1}}>
              Код из Google Authenticator, Aegis или другого TOTP-приложения при каждом входе.
            </span>
            <Btn v="primary" onClick={startTotp}>Включить 2FA</Btn>
          </div>
        )}

        {setup && (
          <div style={{display:"flex",gap:18,flexWrap:"wrap",alignItems:"center"}}>
            <div style={{background:"#fff",borderRadius:"var(--radius-lg)",padding:8,lineHeight:0}}
              dangerouslySetInnerHTML={{__html:setup.qr_svg}}/>
            <div style={{flex:1,minWidth:200,display:"flex",flexDirection:"column",gap:10}}>
              <div style={{fontSize:12,color:"var(--muted)"}}>
                Отсканируйте QR в приложении или введите ключ вручную:
              </div>
              <code style={{fontFamily:"var(--mono)",fontSize:14,wordBreak:"break-all"}}>{setup.secret}</code>
              <div style={{display:"flex",gap:10}}>
                <input inputMode="numeric" placeholder="000000" value={code}
                  onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,6))} style={codeStyle}/>
                <Btn v="primary" disabled={code.length!==6} onClick={enableTotp}>Подтвердить</Btn>
                <Btn onClick={()=>setSetup(null)}>Отмена</Btn>
              </div>
            </div>
          </div>
        )}

        {session?.totp_enabled && (
          <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
            <input type="password" placeholder="Пароль" value={offPass}
              onChange={e=>setOffPass(e.target.value)} style={inputStyle}/>
            <input inputMode="numeric" placeholder="Код" value={code}
              onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,6))} style={codeStyle}/>
            <Btn v="danger" disabled={!offPass||code.length!==6} onClick={disableTotp}>Отключить 2FA</Btn>
          </div>
        )}
      </div>
    </Card>
  );
};
