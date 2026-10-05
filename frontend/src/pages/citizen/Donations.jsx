import {useState} from 'react';
import {Heart,HeartHandshake} from 'lucide-react';
import {api} from '../../services/api';
import {Badge,Button,ErrorNotice,Field,FormActions,Modal,Panel,ResourceState,SectionTitle,Select,TextArea,date} from '../../components/shared/ui';
import {useData} from '../../hooks/useData';
import ItemRows from '../../components/shared/ItemRows';

let checkoutScript;
function loadCheckout(){
  if(window.Razorpay)return Promise.resolve();
  if(!checkoutScript)checkoutScript=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://checkout.razorpay.com/v1/checkout.js';script.onload=()=>window.Razorpay?resolve():reject(new Error('Payment checkout could not be initialized.'));script.onerror=()=>{script.remove();checkoutScript=null;reject(new Error('Payment checkout could not be loaded.'));};document.head.appendChild(script);});
  return checkoutScript;
}
const support=pledge=>pledge.kind==='money'?`₹${Number(pledge.amount).toLocaleString('en-IN')}`:pledge.items?.map(item=>`${item.quantity} ${item.unit||'units'} ${item.item}`).join(', ');

export default function Donations({user,notify}){
  const resource=useData('/donations/campaigns',{poll:15000}),pledges=useData('/donations/my',{poll:15000}),payment=useData('/donations/payment-config',{initial:null});
  const [campaign,setCampaign]=useState(null),[proof,setProof]=useState(null),[kind,setKind]=useState('money'),[amount,setAmount]=useState(500),[items,setItems]=useState([{item:'',quantity:1}]),[note,setNote]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState('');
  async function pledge(e){e.preventDefault();setBusy('pledge');setError('');try{const saved=await api('/donations/pledges',{method:'POST',body:{campaign_id:campaign.id,kind,amount:kind==='money'?Number(amount):null,items:kind==='supplies'?items.map(item=>({...item,quantity:Number(item.quantity)})):null,note}});notify('Donation commitment saved. Submit a transfer or delivery reference for verification.');setCampaign(null);setProof(saved);pledges.reload();resource.reload();}catch(err){setError(err.message);}finally{setBusy('');}}
  async function payOnline(pledge){
    setBusy(`pay-${pledge.id}`);setError('');
    try{
      const order=await api('/donations/create-payment',{method:'POST',body:{pledge_id:pledge.id}});
      await loadCheckout();
      await new Promise((resolve,reject)=>{
        const checkout=new window.Razorpay({key:order.key_id,amount:order.amount_minor,currency:order.currency||'INR',order_id:order.order_id,name:'ResQ Kerala',description:`Donation commitment #${pledge.id}`,prefill:{name:user.name,email:user.email},handler:async(response)=>{try{await api('/donations/payment-success',{method:'POST',body:{razorpay_order_id:response.razorpay_order_id,razorpay_payment_id:response.razorpay_payment_id,razorpay_signature:response.razorpay_signature}});resolve();}catch(err){reject(err);}},modal:{ondismiss:()=>reject(new Error('Checkout closed. Your donation remains uncollected.'))}});
        checkout.on('payment.failed',response=>reject(new Error(response.error?.description||'Payment was not completed.')));
        checkout.open();
      });
      notify('Provider-confirmed payment receipt recorded.');pledges.reload();resource.reload();
    }catch(err){setError(err.message);}finally{setBusy('');}
  }
  const configured=payment.data?.checkout_configured===true;
  return <>
    <SectionTitle eyebrow="SMALL ACTS. SHARED STRENGTH." title="Support your community" description="Donate money or supplies, then follow the receipt through coordinator verification." action={<Button variant="secondary" onClick={()=>{pledges.reload();resource.reload();}}>Refresh donations</Button>}/>
    <div className="pledge-notice"><HeartHandshake size={22}/><div><strong>Choose a verified donation method.</strong><p>Cash, bank transfer and supplies require a delivery reference and coordinator receipt. {configured?'Online checkout is available; only a provider-confirmed payment produces a receipt.':'Online checkout is not configured. No card payment is taken here.'}</p>{payment.data?.sandbox_enabled?<p>Payment provider test mode: no real funds are transferred.</p>:null}</div></div>
    <ErrorNotice message={error}/>
    <ResourceState resource={resource} emptyTitle="No campaigns yet" emptyBody="Community support campaigns will appear here."><div className="campaign-grid">{resource.data.map(item=><article className="campaign-card panel" key={item.id}><div className="campaign-art"><HeartHandshake size={48}/><span>TOGETHER, FOR KERALA</span></div><div className="campaign-body"><Badge value={item.active?'active':'closed'}/><h2>{item.title}</h2><p>{item.description}</p><div className="campaign-target"><strong>₹{Number(item.received_amount||0).toLocaleString('en-IN')}<small>verified receipts</small></strong><span>₹{Number(item.target_amount).toLocaleString('en-IN')}<small>target</small></span></div><p className="fine-print">₹{Number(item.pledged_amount||item.total_pledged||0).toLocaleString('en-IN')} committed; pending donations are not counted as received.</p>{item.active?<Button variant="secondary full-width" onClick={()=>{setCampaign(item);setError('');}}>Donate money or supplies<Heart size={16}/></Button>:null}</div></article>)}</div></ResourceState>
    <Panel title="Your donations" subtitle="A donation is received only after provider confirmation or a coordinator’s receipt."><ResourceState resource={pledges} emptyTitle="No donations recorded"><div className="request-list">{pledges.data.map(item=><article className="relief-request" key={item.id}><div className="request-header"><div><strong>{item.campaign_title||resource.data.find(row=>row.id===item.campaign_id)?.title||`Campaign #${item.campaign_id}`}</strong><small>Donation #{item.id} · {date(item.created_at)}</small></div><Badge value={item.status}/></div><p>{support(item)}</p>{item.proof_reference?<p className="fine-print">Submitted reference: {item.proof_reference} · {item.proof_method}</p>:null}{item.receipt?<DonationReceipt receipt={item.receipt}/>:<div className="action-row">{['pledged','rejected'].includes(item.status)?<Button variant="secondary small" onClick={()=>setProof(item)}>Submit transfer / delivery reference</Button>:null}{item.kind==='money'&&configured&&['pledged','rejected'].includes(item.status)?<Button variant="secondary small" busy={busy===`pay-${item.id}`} onClick={()=>payOnline(item)}>Pay with Razorpay{payment.data?.sandbox_enabled?' (test mode)':''}</Button>:null}{item.status==='pending_verification'?<p className="muted">Awaiting coordinator verification. No receipt has been issued.</p>:null}</div>}</article>)}</div></ResourceState></Panel>
    {campaign?<Modal title={`Support ${campaign.title}`} onClose={()=>setCampaign(null)}><form onSubmit={pledge}><div className="segmented"><button type="button" className={kind==='money'?'selected':''} onClick={()=>setKind('money')}>Donate money</button><button type="button" className={kind==='supplies'?'selected':''} onClick={()=>setKind('supplies')}>Donate supplies</button></div>{kind==='money'?<Field label="Donation amount (₹)" required type="number" min={1} max={10000000} step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/>:<ItemRows items={items} setItems={setItems}/>}<TextArea label="Coordination note (optional)" value={note} onChange={e=>setNote(e.target.value)} maxLength={2000}/><p className="fine-print">This step records your commitment. Submit a payment or delivery reference next.</p><ErrorNotice message={error}/><FormActions busy={busy==='pledge'} label="Continue donation" onCancel={()=>setCampaign(null)}/></form></Modal>:null}
    {proof?<DonationProof pledge={proof} onClose={()=>setProof(null)} onSaved={()=>{pledges.reload();resource.reload();}} notify={notify}/>:null}
  </>;
}
export function DonationReceipt({receipt}){
  return <div className="distribution-notes" aria-label="Verified donation receipt"><strong>Receipt #{receipt.id} · {receipt.method}</strong><p>Reference: {receipt.reference} · Confirmed {date(receipt.created_at)}</p>{receipt.sandbox?<p className="fine-print">Provider sandbox receipt. No real funds were transferred.</p>:<p className="fine-print">Verified by the coordinator or payment provider.</p>}</div>;
}
function DonationProof({pledge,onClose,onSaved,notify}){
  const [method,setMethod]=useState(pledge.kind==='supplies'?'supplies':'bank_transfer'),[reference,setReference]=useState(''),[note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(e){e.preventDefault();setBusy(true);setError('');try{await api(`/donations/${pledge.id}/submit-proof`,{method:'POST',body:{method,reference,note}});notify('Reference submitted. A coordinator will verify receipt before recording the donation as received.');onSaved();onClose();}catch(err){setError(err.message);}finally{setBusy(false);}}
  return <Modal title={`Submit donation reference #${pledge.id}`} onClose={onClose}><form onSubmit={submit}><p>{support(pledge)}</p><Select label="Donation method" required value={method} onChange={e=>setMethod(e.target.value)} options={pledge.kind==='supplies'?[{value:'supplies',label:'Supplies handed over'}]:[{value:'bank_transfer',label:'Bank transfer'},{value:'cash',label:'Cash handed over'}]}/><Field label="Transfer / delivery reference" required minLength={3} maxLength={200} value={reference} onChange={e=>setReference(e.target.value)}/><TextArea label="Receipt note (optional)" maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/><p className="fine-print">Submit a reference for an actual transfer or handover. This form does not transfer money or arrange delivery.</p><ErrorNotice message={error}/><FormActions busy={busy} label="Submit for verification" onCancel={onClose}/></form></Modal>;
}
