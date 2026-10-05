import {useData} from '../../hooks/useData';
import DashboardView from '../../components/shared/DashboardView';

export default function Dashboard({user,navigate,notify}) {
  const incidents = useData('/incidents/my', {poll:15000});
  const alerts = useData('/alerts');
  const shelters = useData('/shelters');
  const news = useData('/news');
  const safety = useData('/safety-tips');
  const teams = {data:[],reload:()=>{}};
  
  const active=incidents.data.filter(i=>!['resolved','closed'].includes(i.status)),high=incidents.data.filter(i=>i.severity==='high'),review=incidents.data.filter(i=>['submitted','under_review'].includes(i.status));
  const ownTeam=teams.data.find(t=>t.id===user.team_id),capacity=shelters.data.reduce((sum,s)=>sum+Math.max(0,s.capacity-s.occupied),0);
  const displayAlerts=alerts.data.filter(a=>a.active!==false&&(!a.expires_at||new Date(a.expires_at)>new Date()));
  const resolved=incidents.data.filter(i=>['resolved','closed'].includes(i.status)).length;
  return <DashboardView user={user} navigate={navigate} notify={notify} incidents={incidents} alerts={alerts} shelters={shelters} teams={teams} news={news} safety={safety} active={active} high={high} review={review} ownTeam={ownTeam} capacity={capacity} displayAlerts={displayAlerts} resolved={resolved}/>;
}
