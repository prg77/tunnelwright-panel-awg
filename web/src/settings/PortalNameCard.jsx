import React, { useState, useEffect } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";

// ─── PortalNameCard ─────────────────────────────────────────────
export const PortalNameCard = ({ config, setConfig, push }) => {
  const [val, setVal] = useState(config.portal_name || "Private World");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (config.portal_name) setVal(config.portal_name); }, [config.portal_name]);
  const save = async () => {
    const name = val.trim();
    setSaving(true);
    try {
      const s = await api.saveSettings({portal_name:name});
      setConfig(c => ({...c, ...s}));
      push({type:"ok", title:"Название сохранено", detail:name});
    } catch (e) { push({type:"err", title:"Не сохранено", detail:e.message}); }
    finally { setSaving(false); }
  };
  return (
    <Card>
      <CardH sub="отображается на странице входа и в боковом меню">Название панели</CardH>
      <div style={{padding:"12px 16px",display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <input value={val} onChange={e=>setVal(e.target.value.slice(0,15))} maxLength={15}
          placeholder="Private World" style={{flex:1,minWidth:140}}/>
        <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)",flexShrink:0}}>{val.length}/15</span>
        <Btn v="primary" disabled={saving||!val.trim()} onClick={save}>{saving?"Сохранение…":"Сохранить"}</Btn>
      </div>
    </Card>
  );
};
