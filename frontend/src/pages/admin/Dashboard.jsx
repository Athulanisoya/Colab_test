import {useState} from 'react';
import {api} from '../../services/api';
import {Badge,Button,ErrorNotice,Field,Panel,ResourceState,date} from '../../components/shared/ui';
import {useData} from '../../hooks/useData';
import DashboardView from '../../components/shared/DashboardView';

export default function Dashboard({user,navigate,notify}) {
  const monitoring=useData('/admin/monitoring',{poll:15000});
  const overview = useData('/admin/dashboard', {initial:null,poll:15000});
  const incidents = useData('/incidents', {poll:15000});
  const alerts = useData('/alerts');
  const shelters = useData('/shelters');
  const news = useData('/news');
  const safety = useData('/safety-tips');
  const teams = useData('/teams');
  
  const active=incidents.data.filter(i=>!['resolved','closed'].includes(i.status)),high=active.filter(i=>i.severity==='high'),review=incidents.data.filter(i=>['submitted','under_review'].includes(i.status));
  const ownTeam=teams.data.find(t=>t.id===user.team_id),capacity=shelters.data.reduce((sum,s)=>sum+Math.max(0,s.capacity-s.occupied),0);
  const displayAlerts=alerts.data.filter(a=>a.active!==false&&(!a.expires_at||new Date(a.expires_at)>new Date()));
  const resolved=incidents.data.filter(i=>['resolved','closed'].includes(i.status)).length;
  return <><DashboardView user={user} navigate={navigate} notify={notify} incidents={incidents} alerts={alerts} shelters={shelters} teams={teams} news={news} safety={safety} active={active} high={high} review={review} ownTeam={ownTeam} capacity={capacity} displayAlerts={displayAlerts} resolved={resolved} overview={overview}/><Panel title="Alert areas without citizen reports" subtitle="An absence of reports does not establish that an area is safe. Record monitoring or request field investigation."><ResourceState resource={monitoring} emptyTitle="No alert areas to monitor">{monitoring.data.map(area=><MonitoringArea key={area.alert_id||area.id} area={area} onSaved={monitoring.reload} notify={notify}/>)}</ResourceState></Panel></>;
}
function MonitoringArea({area,onSaved,notify}) {
  const [note,setNote]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState('');
  async function decide(action){setBusy(action);setError('');try{await api(`/admin/monitoring/${area.alert_id||area.id}`,{method:'POST',body:{action,note}});notify(action==='investigate'?'Investigation decision recorded.':'Monitoring decision recorded.');setNote('');onSaved();}catch(err){setError(err.message);}finally{setBusy('');}}
  return <article className="field-finding"><div className="inline"><strong>{area.title||area.location} · {area.district}</strong><Badge value={area.status}/></div><p>{area.report_count||0} citizen reports · Latest report: {date(area.last_report_at)}</p>{area.monitoring_note?<p>Coordinator note: {area.monitoring_note}</p>:null}<Field label={`Monitoring note for ${area.location}`} minLength={5} maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/><ErrorNotice message={error}/><div className="action-row"><Button variant="secondary small" disabled={note.trim().length<5} busy={busy==='monitor'} onClick={()=>decide('monitor')}>Record monitoring</Button><Button variant="secondary small" disabled={note.trim().length<5} busy={busy==='investigate'} onClick={()=>decide('investigate')}>Request field investigation</Button></div></article>;
}

