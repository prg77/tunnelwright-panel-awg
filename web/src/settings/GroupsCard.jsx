import React, { useState } from "react";
import { api } from "../api";
import { Card, CardH, Btn } from "../components/ui";
import { groupsStore, useGroups } from "../stores/groups";

const PALETTE = ["#f472b6","#60a5fa","#fbbf24","#a78bfa","#34d399","#f87171","#22d3ee","#fb923c","#94a3b8"];
const inp = {background:"var(--surface2)",border:"1px solid var(--border)",borderRadius:"var(--radius)",color:"var(--text)",
             padding:"6px 10px",fontSize:14,fontFamily:"var(--sans)",minWidth:0};

// ─── Строка группы: имя, цвет, порядок, удаление ─────────────────
const GroupRow = ({ g, first, last, onMove, onSave, onDelete }) => {
  const [name, setName] = useState(g.name);
  const [pick, setPick] = useState(false);
  const dirty = name.trim() && name.trim() !== g.name;
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,padding:"7px 18px",borderBottom:"1px solid var(--border)",flexWrap:"wrap"}}>
      <div style={{position:"relative"}}>
        <button onClick={() => setPick(p => !p)} title="Цвет"
          style={{width:20,height:20,borderRadius:"50%",background:g.color,border:"2px solid var(--surface2)",cursor:"pointer"}}/>
        {pick && <div style={{position:"absolute",zIndex:5,top:26,left:0,display:"flex",gap:5,padding:7,background:"var(--surface)",
          border:"1px solid var(--border)",borderRadius:"var(--radius)",boxShadow:"0 6px 18px rgba(0,0,0,.25)"}}>
          {PALETTE.map(c => <button key={c} onClick={() => { setPick(false); onSave({color:c}); }}
            style={{width:18,height:18,borderRadius:"50%",background:c,cursor:"pointer",border:c===g.color?"2px solid var(--text)":"none"}}/>)}
        </div>}
      </div>
      <input value={name} onChange={e => setName(e.target.value)} maxLength={32} style={{...inp,flex:"1 1 140px"}}
        onKeyDown={e => { if (e.key === "Enter" && dirty) onSave({name:name.trim()}); }}/>
      {dirty && <Btn v="primary" onClick={() => onSave({name:name.trim()})} style={{height:28}}>Сохранить</Btn>}
      <span style={{fontSize:12,color:"var(--muted)",minWidth:70,textAlign:"right"}}>клиентов: {g.clients}</span>
      <Btn v="ghost" disabled={first} onClick={() => onMove(-1)} title="Выше" style={{height:28,padding:"0 8px"}}>↑</Btn>
      <Btn v="ghost" disabled={last} onClick={() => onMove(1)} title="Ниже" style={{height:28,padding:"0 8px"}}>↓</Btn>
      <Btn v="danger" onClick={onDelete} title="Удалить" style={{height:28,padding:"0 9px"}}>✕</Btn>
    </div>
  );
};

// ─── GroupsCard — группы клиентов ────────────────────────────────
export const GroupsCard = ({ push, setConfirmModal, onChanged }) => {
  const { list } = useGroups();
  const [newName, setNewName] = useState("");
  const err = (e) => push({type:"err", title:"Группы", detail:e.message});
  const changed = () => groupsStore.reload().then(onChanged);

  const add = async () => {
    try {
      await api.addGroup({name:newName.trim(), color:PALETTE[list.length % PALETTE.length]});
      setNewName(""); groupsStore.reload();
    } catch (e) { err(e); }
  };
  const save = (g) => async (patch) => {
    try { await api.updateGroup(g.id, patch); changed(); } catch (e) { err(e); }
  };
  const move = (i) => async (d) => {
    const ids = list.map(g => g.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    try { groupsStore.set(await api.orderGroups(ids)); } catch (e) { err(e); }
  };
  const del = (g) => setConfirmModal({
    title: `Удалить группу «${g.name}»?`,
    detail: g.clients ? `Клиенты группы (${g.clients}) останутся без группы.` : "В группе нет клиентов.",
    onConfirm: async () => { try { await api.delGroup(g.id); changed(); } catch (e) { err(e); } },
  });

  return (
    <Card>
      <CardH sub="группы для фильтра и наглядности; на маршрутизацию не влияют">Группы клиентов</CardH>
      {list.map((g, i) => (
        <GroupRow key={`${g.id}-${g.name}`} g={g} first={i === 0} last={i === list.length - 1}
          onMove={move(i)} onSave={save(g)} onDelete={() => del(g)}/>
      ))}
      <div style={{display:"flex",gap:8,padding:"10px 18px"}}>
        <input value={newName} onChange={e => setNewName(e.target.value)} maxLength={32} placeholder="Новая группа"
          style={{...inp,flex:1}} onKeyDown={e => { if (e.key === "Enter" && newName.trim()) add(); }}/>
        <Btn v="primary" onClick={add} disabled={!newName.trim()}>Добавить</Btn>
      </div>
    </Card>
  );
};
