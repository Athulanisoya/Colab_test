import {Activity,ArrowDownToLine,CheckCircle2,Heart,Tent,Users} from 'lucide-react';
import {Badge,Button,Empty,ErrorNotice,Loading,Panel,SectionTitle,Stat,date,label,shelterAvailable} from '../../components/shared/ui';
import {useData} from '../../hooks/useData';

function Breakdown({title,values}) {
  const entries=Object.entries(values||{}).filter(([,value])=>typeof value==='number');
  const max=Math.max(...entries.map(([,count])=>count),1);
  return <Panel title={title}>{entries.length?<div className="breakdown">{entries.map(([name,count])=><div key={name}><span>{label(name)}</span><div><i style={{width:`${count/max*100}%`}}/></div><strong>{count}</strong></div>)}</div>:<p className="muted">No aggregate data available yet.</p>}</Panel>;
}

function DataTable({headers,rows,renderRow,empty}) {
  if(!rows.length)return <Empty title={empty} body="Recorded activity will appear here."/>;
  return <div className="table-scroll"><table><thead><tr>{headers.map(title=><th key={title}>{title}</th>)}</tr></thead><tbody>{rows.map(renderRow)}</tbody></table></div>;
}

export default function Reports() {
  const resource=useData('/admin/reports',{initial:null});
  const incidents=useData('/incidents');
  const pledges=useData('/donations/pledges');
  const campaigns=useData('/admin/campaigns');
  const receipts=useData('/donations/records');
  const r=resource.data||{},teams=r.teams||[],shelters=r.shelters||[],inventory=r.inventory||[],donations=r.donations||{};
  const countBy=(rows,key)=>rows.reduce((counts,row)=>{const value=row[key]||'unknown';counts[value]=(counts[value]||0)+1;return counts;},{});
  const teamTypes=countBy(teams,'team_type');
  const supplyPledges=pledges.data.filter(pledge=>pledge.kind==='supplies').length;
  function download() {
    const payload={generated_at:new Date().toISOString(),report_aggregates:r,pledge_records:pledges.data,donation_receipts:receipts.data};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='resq-kerala-report.json';anchor.click();URL.revokeObjectURL(url);
  }
  return <>
    <SectionTitle eyebrow="TURN ACTIVITY INTO INSIGHT" title="Response reports" description="Disaster, relief, team, shelter and donation reports from the local workspace. Seeded demo records are included." action={<Button variant="secondary" onClick={download} disabled={!resource.data}><ArrowDownToLine size={16}/>Export aggregates</Button>}/>
    <ErrorNotice message={resource.error} onRetry={resource.reload}/>
    {resource.loading&&!resource.data?<Loading/>:<>
      <div className="stats-grid">
        <Stat title="Total reports" value={incidents.data.length} icon={Activity} detail="All statuses"/>
        <Stat title="Completed responses" value={incidents.data.filter(row=>['resolved','closed'].includes(row.status)).length} icon={CheckCircle2} detail="Resolved or closed"/>
        <Stat title="Response teams" value={teams.length} icon={Users} detail={`${teams.filter(team=>team.available).length} available`}/>
        <Stat title="Shelter occupancy" value={`${shelters.reduce((n,row)=>n+row.occupied,0)} / ${shelters.reduce((n,row)=>n+row.capacity,0)}`} icon={Tent} detail="People / total capacity"/>
      </div>
      <section aria-label="Disaster reports"><h2>Disaster reports</h2><div className="report-charts">
        <Breakdown title="Reports by status" values={r.incidents_by_status||countBy(incidents.data,'status')}/>
        <Breakdown title="Reports by district" values={r.incidents_by_district||countBy(incidents.data,'district')}/>
        <Breakdown title="Severity suggestions" values={r.incidents_by_severity||countBy(incidents.data,'severity')}/>
      </div></section>
      <section aria-label="Relief reports"><h2>Relief reports</h2><div className="report-charts">
        <Breakdown title="Relief requests by status" values={r.relief_requests_by_status}/>
        <Panel title="Recorded distributions"><p className="capacity-line"><strong>{r.distributions??0}</strong><span>distribution records</span></p><p className="muted">Each distribution deducts stock and tracks the requested quantity.</p></Panel>
      </div><Panel title="Relief inventory report"><DataTable headers={['Item','Stock','Unit','Storage location']} rows={inventory} empty="No inventory recorded" renderRow={row=><tr key={row.id}><td><strong>{row.item}</strong></td><td>{row.quantity}</td><td>{row.unit}</td><td>{row.location}</td></tr>}/></Panel></section>
      <section aria-label="Team reports"><h2>Team reports</h2><Breakdown title="Teams by responsibility" values={teamTypes}/><Panel title="Team availability report"><DataTable headers={['Team','Responsibility','District','Availability']} rows={teams} empty="No teams recorded" renderRow={team=><tr key={team.id}><td><strong>{team.name}</strong></td><td>{label(team.team_type)}</td><td>{team.district}</td><td><Badge value={team.available?'available':'busy'}/></td></tr>}/></Panel></section>
      <section aria-label="Shelter reports"><h2>Shelter reports</h2><Panel title="Shelter capacity report"><DataTable headers={['Shelter','District','Capacity','Occupied','Available spaces','Facilities']} rows={shelters} empty="No shelters recorded" renderRow={shelter=><tr key={shelter.id}><td><strong>{shelter.name}</strong><small>{shelter.location}</small></td><td>{shelter.district}</td><td>{shelter.capacity}</td><td>{shelter.occupied}</td><td>{shelterAvailable(shelter)}</td><td>{shelter.facilities?.join(', ')||'Not listed'}</td></tr>}/></Panel></section>
      <section aria-label="Donation reports"><h2>Donation reports</h2><div className="stats-grid">
        <Stat title="Support pledges" value={donations.pledges??pledges.data.length} icon={Heart} detail="Recorded commitments"/>
        <Stat title="Money pledged" value={`₹${Number(donations.total_pledged_money||0).toLocaleString('en-IN')}`} icon={Heart} detail="Committed amounts include pending donations"/>
        <Stat title="Supply pledges" value={supplyPledges} icon={Heart} detail="Supply commitments, including received donations"/>
        <Stat title="Payment processing" value={label(donations.payment_status||'disabled')} icon={Heart} detail="Offline receipts plus configured provider checkout"/>
      </div><div className="stats-grid"><Stat title="Verified donation receipts" value={donations.received_records??receipts.data.filter(row=>!row.sandbox).length} icon={Heart} detail="Excludes provider sandbox simulations"/><Stat title="Money received" value={`₹${Number(donations.received_money||0).toLocaleString('en-IN')}`} icon={Heart} detail="Coordinator or provider-confirmed"/><Stat title="Supplies received" value={donations.received_supplies??0} icon={Heart} detail="Verified supply donation receipts"/><Stat title="Sandbox receipts" value={donations.sandbox_records??0} icon={Heart} detail="Test records; no funds transferred"/></div><Panel title="Donation receipt report"><ErrorNotice message={receipts.error} onRetry={receipts.reload}/><DataTable headers={['Receipt','Donation','Kind','Method / reference','Confirmation']} rows={receipts.data} empty="No donation receipts" renderRow={receipt=><tr key={receipt.id}><td>#{receipt.id}</td><td>#{receipt.pledge_id}</td><td>{receipt.kind}</td><td>{receipt.method}<small>{receipt.reference}</small></td><td>{date(receipt.created_at)}{receipt.sandbox?<small>Sandbox — no real transfer</small>:null}</td></tr>}/></Panel><Panel title="Donation pledge report"><ErrorNotice message={pledges.error} onRetry={pledges.reload}/><DataTable headers={['Campaign','Kind','Pledged support','Status','Recorded']} rows={pledges.data} empty="No pledges recorded" renderRow={pledge=><tr key={pledge.id}><td>{campaigns.data.find(campaign=>campaign.id===pledge.campaign_id)?.title||`Campaign #${pledge.campaign_id}`}</td><td><Badge value={pledge.kind}/></td><td>{pledge.kind==='money'?`₹${Number(pledge.amount).toLocaleString('en-IN')}`:pledge.items?.map(item=>`${item.quantity} ${item.item}`).join(', ')}</td><td><Badge value={pledge.status}/></td><td>{date(pledge.created_at)}</td></tr>}/></Panel></section>
    </>}
  </>;
}
