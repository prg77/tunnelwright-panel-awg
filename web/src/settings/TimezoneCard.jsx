import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";
import { setPanelTz } from "../utils/time";

// ─── TimezoneCard — часовой пояс панели (часы, отметки времени, границы суток в статистике)
export const TimezoneCard = ({ config, setConfig, push }) => {
  const [zones, setZones] = useState([]);
  const [val, setVal] = useState(config.timezone || "Europe/Moscow");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.timezones().then(setZones).catch(() => {}); }, []);
  useEffect(() => { if (config.timezone) setVal(config.timezone); }, [config.timezone]);

  const save = async () => {
    setBusy(true);
    try {
      await api.saveSettings({timezone: val});
      setPanelTz(val);
      setConfig(c => ({...c, timezone: val}));
      push({type:"ok", title:"Часовой пояс сохранён", detail:val});
    } catch (e) { push({type:"err", title:"Ошибка", detail:e.message}); }
    finally { setBusy(false); }
  };

  return (
    <Card>
      <CardH sub="часы, время в уведомлениях и границы суток в статистике трафика">Часовой пояс</CardH>
      <div style={{padding:"12px 18px",display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <select value={val} onChange={e=>setVal(e.target.value)}
          style={{flex:1,minWidth:200,background:"var(--bg)",border:"1px solid var(--border)",
            borderRadius:"var(--radius)",color:"var(--text)",fontSize:14,padding:"8px 12px"}}>
          {(zones.length ? zones : [val]).map(z => <option key={z} value={z}>{z.replace(/_/g," ")}</option>)}
        </select>
        <span style={{fontSize:12,color:"var(--muted)",fontFamily:"var(--mono)"}}>
          {new Date().toLocaleTimeString("ru",{timeZone:val,hour:"2-digit",minute:"2-digit"})}
        </span>
        <Btn v="primary" disabled={busy||val===config.timezone} onClick={save}>Сохранить</Btn>
      </div>
    </Card>
  );
};
