import {useEffect,useRef,useState} from 'react';
import {http} from '../services/http';

const POLL_MS=3000;

/** Whether this server can send M-Pesa prompts. null while loading. */
export function useMpesaEnabled(){
 const [enabled,setEnabled]=useState(null);
 useEffect(()=>{let live=true;http.get('/api/mpesa/config').then(c=>live&&setEnabled(!!c?.enabled)).catch(()=>live&&setEnabled(false));return()=>{live=false}},[]);
 return enabled;
}

/**
 * Sends an M-Pesa prompt to the customer's phone and follows it until it is paid or fails.
 * target: {order_id, expected_version} or {carwash_id}. onPaid(prompt) runs once when paid.
 */
export default function MpesaPrompt({target,amount,onPaid,disabled}){
 const [phone,setPhone]=useState(''),[prompt,setPrompt]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const done=useRef(false),paidRef=useRef(onPaid);paidRef.current=onPaid;
 const waiting=prompt?.status==='waiting';
 useEffect(()=>{
  if(!waiting)return;
  const timer=setInterval(async()=>{try{const next=await http.get('/api/mpesa/prompts/'+prompt.id);setPrompt(next)}catch{/* keep polling; the network may be back next time */}},POLL_MS);
  return()=>clearInterval(timer);
 },[waiting,prompt?.id]);
 useEffect(()=>{if(prompt?.status==='paid'&&!done.current){done.current=true;paidRef.current?.(prompt)}},[prompt]);
 async function send(){if(busy||!phone.trim())return;setBusy(true);setError('');
  try{setPrompt(await http.post('/api/mpesa/prompts',{...target,phone}))}catch(err){setError(err.message)}finally{setBusy(false)}}
 async function stop(){setBusy(true);try{setPrompt(await http.post('/api/mpesa/prompts/'+prompt.id+'/stop',{}))}catch(err){setError(err.message)}finally{setBusy(false)}}
 if(waiting)return <div className="mpesa-prompt" role="status" aria-live="polite"><strong>Prompt sent to {prompt.phone}</strong><p>{prompt.message}</p><p className="muted">This updates by itself. If the customer pays another way, stop waiting first.</p><button type="button" className="btn" disabled={busy} onClick={stop}>Stop waiting</button></div>;
 if(prompt?.status==='paid')return <div className="mpesa-prompt paid" role="status"><strong>M-Pesa payment received</strong><p>{prompt.message}</p></div>;
 // Not a <form>: it sits inside the checkout form.
 return <div className="mpesa-prompt" role="group" aria-label="Send M-Pesa prompt">
  <label className="field">Customer's M-Pesa number<input type="tel" inputMode="tel" autoComplete="off" placeholder="0712 345 678" value={phone} onChange={e=>setPhone(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();send()}}} disabled={disabled||busy}/></label>
  {prompt&&prompt.status!=='paid'&&<p className="cashier-warning" role="status">{prompt.message}</p>}
  {error&&<p className="cashier-warning" role="alert">{error}</p>}
  <button type="button" className="btn primary" onClick={send} disabled={disabled||busy||!phone.trim()}>{busy?'Sending…':prompt?'Send the prompt again':'Send M-Pesa prompt'}{amount!=null?' · KES '+Number(amount).toLocaleString():''}</button>
 </div>;
}

/** Managers: M-Pesa payments that arrived but could not be applied (bill already paid, amount changed). */
export function MpesaAttention(){
 const [rows,setRows]=useState(null),[note,setNote]=useState({}),[error,setError]=useState('');
 const load=()=>http.get('/api/mpesa/prompts?status=unmatched').then(setRows).catch(e=>setError(e.message));
 useEffect(()=>{load()},[]);
 async function resolve(id){setError('');try{await http.post('/api/mpesa/prompts/'+id+'/resolve',{note:note[id]||''});load()}catch(e){setError(e.message)}}
 if(!rows?.length)return error?<p role="alert">{error}</p>:null;
 return <section className="panel mpesa-attention" aria-label="M-Pesa payments needing attention"><h2>M-Pesa payments needing attention</h2>
  <p>The customer paid, but the bill or car wash could no longer take the money. Refund the customer or settle it by hand, then note what you did.</p>
  {error&&<p role="alert">{error}</p>}
  <ul>{rows.map(r=><li key={r.id}><strong>KES {Number(r.amount).toLocaleString()}</strong> from {r.phone}{r.receipt?' · receipt '+r.receipt:''} · {r.order_id?'bill #'+r.order_id:'car wash #'+r.carwash_id}<p>{r.note}</p>
   <label className="field">What was done<input value={note[r.id]||''} onChange={e=>setNote({...note,[r.id]:e.target.value})} placeholder="e.g. Refunded via M-Pesa reversal"/></label>
   <button className="btn" disabled={(note[r.id]||'').trim().length<3} onClick={()=>resolve(r.id)}>Mark as resolved</button></li>)}</ul>
 </section>;
}
