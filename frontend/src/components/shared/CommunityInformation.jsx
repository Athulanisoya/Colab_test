import {useEffect,useRef,useState} from 'react';
import {CheckCircle2,LocateFixed,Shield,ShieldCheck,Tent} from 'lucide-react';
import {api} from '../../services/api';
import {Badge,Button,Empty,ErrorNotice,Field,Location,Panel,ResourceState,SearchBox,SectionTitle,date,districts,label,shelterAvailable} from './ui';
import {useData} from '../../hooks/useData';
export function Alerts({user,notify}){
  const resource=useData('/alerts'),[search,setSearch]=useState('');
  const list=resource.data.filter(a=>[a.title,a.location,a.district].join(' ').toLowerCase().includes(search.toLowerCase())&&(a.active!==false&&(!a.expires_at||new Date(a.expires_at)>new Date())));
  return <><SectionTitle eyebrow="KNOW WHAT’S HAPPENING" title="Flood alerts" description="Coordinator-published alerts for your community. These are demonstration listings." /><div className="page-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search by place or district"/></div><ResourceState resource={resource} emptyTitle="No alerts published" emptyBody="Follow official local announcements for current conditions."><div className="alerts-grid">{list.map(a=><article className={`alert-card ${a.severity}`} key={a.id}><div className="card-top"><span className="alert-icon"><Shield size={22}/></span><Badge value={a.severity}/></div><span className="eyebrow">{a.district}</span><h2>{a.title}</h2><p>{a.message}</p><div className="alert-card-footer"><Location item={a}/><span>{a.active===false?'Inactive':a.expires_at?`Until ${date(a.expires_at)}`:'Active until updated'}</span></div></article>)}</div>{resource.data.length&&!list.length?<Empty title="No matching alerts" body="Try another place or include inactive alerts."/>:null}</ResourceState></>;
}
export function Shelters({user,notify}){
  const resource=useData('/shelters',{poll:20000}),[search,setSearch]=useState(''),[district,setDistrict]=useState('');
  const list=resource.data.filter(s=>[s.name,s.location,s.district].join(' ').toLowerCase().includes(search.toLowerCase())&&(!district||s.district===district));
  return <><SectionTitle eyebrow="A SAFER PLACE TO STAY" title="Shelters & available spaces" description="Search community shelter listings. Contact the coordinator to confirm access and availability." /><NearbyShelters/><div className="page-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search a shelter or location"/><select aria-label="Filter shelters by district" value={district} onChange={e=>setDistrict(e.target.value)}><option value="">All districts</option>{districts.map(d=><option key={d}>{d}</option>)}</select><span className="muted">{list.reduce((n,s)=>n+shelterAvailable(s),0)} spaces across {list.length} shelters</span></div><ResourceState resource={resource} emptyTitle="No shelters listed" emptyBody="Shelter listings will appear when published by the coordinator."><div className="shelter-grid">{list.map(s=>{const available=shelterAvailable(s);return <article className="shelter-card panel" key={s.id}><div className="card-top"><span className="shelter-symbol"><Tent size={27}/></span><Badge value={s.status==='closed'?'closed':available?'available':'full'}>{s.status==='closed'?'Closed':available?'Spaces available':'At capacity'}</Badge></div><span className="eyebrow">{s.district}</span><h2>{s.name}</h2><Location item={s}/><div className="shelter-capacity"><strong>{available}<small>spaces available</small></strong><span>{s.occupied} / {s.capacity}<small>currently occupied</small></span></div><div className="capacity-meter"><i style={{width:`${Math.min(100,s.occupied/s.capacity*100)}%`}}/></div><div className="facilities">{s.facilities?.map(f=><span key={f}><CheckCircle2 size={12}/>{f}</span>)}</div><small className="muted">Demo listing · Confirm before travelling</small></article>;})}</div>{resource.data.length&&!list.length?<Empty title="No shelters match" body="Search another location or district."/>:null}</ResourceState></>;
}
export function News({user,notify,navigate}){
  const resource=useData('/news');
  return <><SectionTitle eyebrow="FROM THE COORDINATION DESK" title="Community news" description="Verified updates, coordination notices, and practical community information." /><ResourceState resource={resource} emptyTitle="No news published yet" emptyBody="Updates from the coordination desk appear here."><div className="news-grid">{resource.data.map((n,index)=><article className={`news-card panel ${index===0?'featured':''}`} key={n.id}><div className="card-top"><span className="eyebrow">COMMUNITY UPDATE</span></div><h2>{n.title}</h2><p className="article-content">{n.content}</p><div className="article-meta"><span>{n.source||'ResQ coordination desk'}</span><span>{date(n.created_at)}</span></div></article>)}</div></ResourceState></>;
}
export function Safety({user,notify}){
  const resource=useData('/safety-tips');
  return <><SectionTitle eyebrow="PREPARE. PROTECT. STAY INFORMED." title="Flood safety guidance" description="Practical safety information from the project knowledge base. Follow local official advice." /><div className="safety-banner"><ShieldCheck size={29}/><div><h2>In immediate danger, call 112.</h2><p>Never enter floodwater to take a photograph or submit a report.</p></div></div><ResourceState resource={resource} emptyTitle="No guidance published" emptyBody="Safety guidance appears here when added by the coordinator."><div className="safety-grid">{resource.data.map((tip,index)=><article className="safety-card panel" key={tip.id||tip.title}><div className="card-top"><span className="safety-number">{String(index+1).padStart(2,'0')}</span><span className="eyebrow">{tip.category||'FLOOD SAFETY'}</span></div><h2>{tip.title}</h2><p className="article-content">{tip.content}</p><small>Source: {tip.source||'Project safety guidance'}</small></article>)}</div></ResourceState></>;
}

export function NearbyShelters() {
  const [latitude,setLatitude]=useState(''),[longitude,setLongitude]=useState(''),[radius,setRadius]=useState(100);
  const [results,setResults]=useState(null),[searchedRadius,setSearchedRadius]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const currentRequest=useRef(null),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;currentRequest.current?.abort();};},[]);
  async function find(lat,lon) {
    if(!mounted.current)return;
    const latNumber=Number(lat),lonNumber=Number(lon),radiusNumber=Number(radius);
    if(String(lat).trim()===''||String(lon).trim()===''||!Number.isFinite(latNumber)||!Number.isFinite(lonNumber)||latNumber< -90||latNumber>90||lonNumber< -180||lonNumber>180||!Number.isFinite(radiusNumber)||radiusNumber<1||radiusNumber>500){setError('Enter valid latitude, longitude and a radius between 1 and 500 km.');setBusy(false);return;}
    currentRequest.current?.abort();
    const controller=new AbortController();currentRequest.current=controller;setBusy(true);setError('');
    try {
      const query=new URLSearchParams({latitude:String(latNumber),longitude:String(lonNumber),radius_km:String(radiusNumber)});
      const nearby=await api(`/shelters/nearby?${query}`,{signal:controller.signal});
      if(!controller.signal.aborted&&mounted.current){setResults(nearby);setSearchedRadius(radiusNumber);}
    }catch(reason){if(reason.name!=='AbortError'&&mounted.current)setError(reason.message);}
    finally{if(mounted.current&&currentRequest.current===controller)setBusy(false);}
  }
  function locate() {
    setError('');
    if(!navigator.geolocation){setError('Location is unavailable in this browser. Enter coordinates below to find nearby shelters.');return;}
    setBusy(true);
    navigator.geolocation.getCurrentPosition(position=>{
      if(!mounted.current)return;
      const lat=position.coords.latitude.toFixed(6),lon=position.coords.longitude.toFixed(6);
      setLatitude(lat);setLongitude(lon);find(lat,lon);
    },()=>{if(mounted.current){setBusy(false);setError('Your location could not be accessed. Enter coordinates below to continue.');}},{enableHighAccuracy:true,timeout:10000});
  }
  return <Panel title="Nearby shelters" subtitle="Use your location or enter coordinates to compare nearby listings." action={<Button type="button" variant="secondary small" busy={busy} onClick={locate}><LocateFixed size={15}/>Use my location</Button>}>
    <form onSubmit={event=>{event.preventDefault();find(latitude,longitude);}}>
      <div className="form-grid">
        <Field label="Latitude" type="number" step="any" min={-90} max={90} required value={latitude} onChange={event=>setLatitude(event.target.value)}/>
        <Field label="Longitude" type="number" step="any" min={-180} max={180} required value={longitude} onChange={event=>setLongitude(event.target.value)}/>
        <Field label="Search radius (km)" type="number" min={1} max={500} required value={radius} onChange={event=>setRadius(event.target.value)}/>
      </div>
      <Button type="submit" variant="secondary small" busy={busy}>Find nearby shelters</Button>
    </form>
    <ErrorNotice message={error}/>
    <p className="fine-print">Distances are approximate straight-line distances, not safe travel routes. Confirm shelter availability with the coordinator before travelling.</p>
    {results!==null?<div aria-live="polite"><p className="muted" role="status">{results.length} {results.length===1?'shelter':'shelters'} found within {searchedRadius} km.</p>{results.length?<div className="mini-shelters">{results.map(shelter=><div key={shelter.id}><span className="mini-icon"><Tent size={21}/></span><h3>{shelter.name}</h3><Location item={shelter}/><p><strong>{Number(shelter.distance_km).toFixed(2)} km</strong> away</p><div className="capacity-line"><strong>{shelter.available_capacity??Math.max(0,shelter.capacity-shelter.occupied)}</strong><span>spaces available</span></div></div>)}</div>:<Empty title="No shelters within this radius" body="Try a larger radius or search the full directory."/>}</div>:null}
  </Panel>;
}
