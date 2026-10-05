import {useEffect,useRef,useState} from 'react';
import {Bot,BookOpen,Send,Sparkles,X} from 'lucide-react';
import {api} from '../../services/api';
import {useData} from '../../hooks/useData';
import {Button,ErrorNotice,Select} from './ui';
const suggestions=['How do I report a flood?','What is the status of my relief requests?','Where can I find a shelter?'];
function answerSource(message){if(message.answerProvider==='authorized_database_snapshot')return 'Authorized application records';if(String(message.grounding||'').startsWith('approved_extracts'))return 'Approved safety guidance';return message.provider?`${message.provider} · ${message.model||'Local model'}`:'Saved response';}
export default function Assistant({onClose}){
  const sessions=useData('/chatbot/sessions');
  const [sessionId,setSessionId]=useState(''),[newConversation,setNewConversation]=useState(false),[messages,setMessages]=useState([]),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[historyBusy,setHistoryBusy]=useState(false),[error,setError]=useState('');
  const end=useRef(null),request=useRef(null),keepLiveHistory=useRef(false);
  useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth',block:'nearest'});},[messages,busy]);
  useEffect(()=>{if(!newConversation&&!sessionId&&sessions.data.length)setSessionId(sessions.data[0].id);},[sessions.data,sessionId,newConversation]);
  useEffect(()=>{
    if(!sessionId){setMessages([]);setHistoryBusy(false);return;}if(keepLiveHistory.current){keepLiveHistory.current=false;return;}
    const controller=new AbortController();setHistoryBusy(true);setError('');setMessages([]);
    api(`/chatbot/history?session_id=${encodeURIComponent(sessionId)}`,{signal:controller.signal}).then(rows=>{if(!controller.signal.aborted)setMessages([...rows].reverse().flatMap(row=>[{role:'user',content:row.message},{role:'assistant',content:row.answer,sources:row.sources||[],provider:row.provider,model:row.model,status:row.status}]));}).catch(err=>{if(err.name!=='AbortError')setError(err.message);}).finally(()=>{if(!controller.signal.aborted)setHistoryBusy(false);});
    return()=>controller.abort();
  },[sessionId]);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function send(text){
    if(text.trim().length<2||text.length>2000||busy||historyBusy)return;
    setInput('');setError('');setMessages(prev=>[...prev,{role:'user',content:text}]);setBusy(true);
    const controller=new AbortController();request.current=controller;
    try{const result=await api('/chatbot/chat',{method:'POST',body:{message:text,...(sessionId?{session_id:Number(sessionId)}:{})},signal:controller.signal});setMessages(prev=>[...prev,{role:'assistant',content:result.answer,sources:result.sources||[],provider:result.provider,model:result.model,status:result.status,answerProvider:result.answer_provider,grounding:result.grounding}]);if(result.session_id&&Number(sessionId)!==result.session_id){keepLiveHistory.current=true;setSessionId(result.session_id);}setNewConversation(false);sessions.reload();}catch(err){if(err.name!=='AbortError')setError(err.message);}finally{if(!controller.signal.aborted)setBusy(false);}
  }
  function startNew(){if(busy)return;setNewConversation(true);setSessionId('');setMessages([]);setError('');setInput('');}
  return <section className="assistant-panel" role="dialog" aria-label="ResQ safety assistant">
    <header><span className="assistant-avatar"><Bot size={22}/></span><div><strong>ResQ assistant</strong><small>Local Gemma 4 · Grounded guidance</small></div><button className="icon-button" onClick={onClose} aria-label="Close assistant"><X size={18}/></button></header>
    <div className="assistant-history"><Select label="Saved conversation" placeholder="New conversation" disabled={busy} options={sessions.data.map(session=>({value:session.id,label:session.title||'Conversation'}))} value={sessionId} onChange={e=>{setNewConversation(!e.target.value);setSessionId(e.target.value);}}/><Button variant="secondary small" type="button" disabled={busy} onClick={startNew}>New conversation</Button></div>
    <div className="assistant-notice"><BookOpen size={14}/>For immediate danger, call 112. AI answers can be incomplete.</div>
    <div className="chat-messages" aria-live="polite">{historyBusy?<p className="muted">Loading your saved conversation…</p>:!messages.length?<div className="chat-welcome"><Sparkles size={29}/><h3>A little guidance,<br/>when you need it.</h3><p>Ask about flood safety, shelters, your reports or relief requests.</p>{suggestions.map(text=><button key={text} onClick={()=>send(text)}>{text}<Send size={13}/></button>)}</div>:messages.map((message,index)=><article className={`chat-message ${message.role}`} key={index}>{message.role==='assistant'?<span className="chat-role"><Bot size={13}/>ResQ assistant</span>:null}<p>{message.content}</p>{message.sources?.length?<div className="chat-sources"><span><BookOpen size={12}/>Retrieved sources</span>{message.sources.map((source,j)=><div key={j}>{typeof source==='object'&&/^https?:\/\//.test(source.url||'')?<a href={source.url} target="_blank" rel="noreferrer">{source.title||source.id||'Safety source'} ↗</a>:typeof source==='string'?source:source.title||source.id||'Application record'}{typeof source==='object'&&source.checked_on?<small>Checked {source.checked_on}</small>:null}</div>)}</div>:null}{message.role==='assistant'?<small className="muted">{answerSource(message)}{message.status?` · ${message.status}`:''}</small>:null}</article>)}{busy?<div className="chat-thinking"><i/><i/><i/><span>Checking local knowledge…</span></div>:null}<ErrorNotice message={error||sessions.error}/><div ref={end}/></div>
    <form className="chat-input" onSubmit={e=>{e.preventDefault();send(input);}}><input aria-label="Message the safety assistant" placeholder="Ask about safety or your relief status…" value={input} onChange={e=>setInput(e.target.value)} minLength={2} maxLength={2000} required/><Button type="submit" disabled={input.trim().length<2||historyBusy} busy={busy} aria-label="Send message"><Send size={17}/></Button></form>
    <footer>AI-assisted guidance · Operational decisions stay with people.</footer>
  </section>;
}
