import {useState} from 'react';
import {Activity} from 'lucide-react';
import {Panel,ResourceState,SearchBox,SectionTitle,date,label} from '../../components/shared/ui';
import {useData} from '../../hooks/useData';

export default function Audit(){
  const resource=useData('/admin/audit-logs'),[search,setSearch]=useState('');
  const logs=resource.data.filter(l=>[l.action,l.entity_type,l.actor_name,typeof l.detail==='object'?JSON.stringify(l.detail):l.detail].join(' ').toLowerCase().includes(search.toLowerCase()));
  return <><SectionTitle eyebrow="A TRACEABLE RESPONSE" title="Activity log" description="Recorded actions across account access, coordination, and supply distribution."/><Panel><div className="table-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search actions or records"/></div><ResourceState resource={resource} emptyTitle="No activity recorded"><div className="table-scroll"><table><thead><tr><th>Action</th><th>Record</th><th>Actor</th><th>Details</th><th>Time</th></tr></thead><tbody>{logs.map(log=><tr key={log.id}><td><strong>{label(log.action)}</strong></td><td>{label(log.entity_type||log.resource_type)} {log.entity_id||log.resource_id||''}</td><td>{log.actor_name||log.user_id||log.actor_id||'System'}</td><td className="audit-details">{typeof log.detail==='object'?JSON.stringify(log.detail):log.detail||'—'}</td><td className="nowrap">{date(log.created_at)}</td></tr>)}</tbody></table></div></ResourceState></Panel></>;
}
