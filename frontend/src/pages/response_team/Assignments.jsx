import {useState} from 'react';
import {useData} from '../../hooks/useData';
import IncidentListView from '../../components/shared/IncidentListView';
import {Badge,Empty,Panel,ResourceState,SearchBox,date,label} from '../../components/shared/ui';

export default function Assignments({user,navigate}) {
  const reports = useData('/incidents', {poll:12000});
  const history = useData('/teams/history', {poll:15000});
  const [historySearch,setHistorySearch] = useState('');
  const [search,setSearch] = useState('');
  const [status,setStatus] = useState('');
  const [severity,setSeverity] = useState('');
  const incidents = reports.data.filter(report=>
    [report.message,report.location,report.district,report.reference].join(' ').toLowerCase().includes(search.toLowerCase()) &&
    (!status || report.status===status) && (!severity || String(report.severity).toLowerCase()===severity)
  );
  const active = reports.data.filter(report=>!['closed','resolved','rejected'].includes(report.status)).length;
  const pastAssignments=history.data.filter(assignment=>[assignment.reference,assignment.assignment_status,assignment.last_status].join(' ').toLowerCase().includes(historySearch.toLowerCase()));
  return <>
    <IncidentListView user={user} navigate={navigate} resource={reports} search={search} setSearch={setSearch} status={status} setStatus={setStatus} severity={severity} setSeverity={setSeverity} incidents={incidents} active={active}/>
    <Panel title="Task history" subtitle="Your team's assignments and the last status recorded during each assignment.">
      <div className="table-toolbar"><SearchBox value={historySearch} onChange={setHistorySearch} placeholder="Search task history"/></div>
      <ResourceState resource={history} emptyTitle="No task history yet" emptyBody="Assignments remain listed here after completion or release.">
        {pastAssignments.length?<div className="table-scroll"><table><thead><tr><th>Report reference</th><th>Assignment</th><th>Last recorded status</th><th>Assigned</th><th>Ended</th></tr></thead><tbody>{pastAssignments.map(assignment=><tr key={assignment.assignment_id}><td><strong>{assignment.reference}</strong></td><td><Badge value={assignment.assignment_status}/></td><td>{label(assignment.last_status)}</td><td>{date(assignment.assigned_at)}</td><td>{assignment.ended_at?date(assignment.ended_at):'Current assignment'}</td></tr>)}</tbody></table></div>:<Empty title="No matching assignments" body="Try another reference or status."/>}
      </ResourceState>
      <p className="fine-print">Released cases show only your team's history. Citizen details and later response activity remain restricted.</p>
    </Panel>
  </>;
}
