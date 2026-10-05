import {useState} from 'react';
import {useData} from '../../hooks/useData';
import IncidentListView from '../../components/shared/IncidentListView';

export default function IncidentQueue({user,navigate}) {
  const reports = useData('/incidents', {poll:12000});
  const [search,setSearch] = useState('');
  const [status,setStatus] = useState('');
  const [severity,setSeverity] = useState('');
  const incidents = reports.data.filter(report=>
    [report.message,report.location,report.district,report.reference].join(' ').toLowerCase().includes(search.toLowerCase()) &&
    (!status || report.status===status) && (!severity || String(report.severity).toLowerCase()===severity)
  );
  const active = reports.data.filter(report=>!['closed','resolved','rejected'].includes(report.status)).length;
  return <IncidentListView user={user} navigate={navigate} resource={reports} search={search} setSearch={setSearch} status={status} setStatus={setStatus} severity={severity} setSeverity={setSeverity} incidents={incidents} active={active}/>;
}
