import {useEffect,useState} from 'react';
import {Link,useNavigate,useSearchParams} from 'react-router-dom';
import {useAuth} from '../auth/AuthContext';
import {request,http} from '../services/http';
import {money,Panel,Field} from './LiveUI';
import WaiterOrderComposer from './WaiterOrderComposer';
import TaxSummary from '../components/TaxSummary';
import FoodPhoto from '../components/FoodPhoto';
import {productImage} from '../services/productImages';

export function useLive(path){
 const [data,setData]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true,sequence=0;
 async function refresh(){const n=++sequence;try{const result=await http.get(path);if(alive&&n===sequence){setData(result);setError('')}}catch(e){if(alive&&n===sequence)setError(e.message)}}
 refresh();const timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
 const focus=()=>{if(!document.hidden)refresh()};window.addEventListener('focus',focus);document.addEventListener('visibilitychange',focus);
 return()=>{alive=false;clearInterval(timer);window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',focus)};
 },[path,revision]);
 return {data,error,reload:()=>setRevision(n=>n+1)};
}
export function LiveState({query}){return query.error?<div role="alert">Connection/request error: {query.error} <button className="btn" onClick={query.reload}>Retry</button></div>:query.data===null?<p role="status">Loading…</p>:null}
const date=s=>new Date(s&&(/[Z+]\d*:?\d*$/.test(s)?s:s+'Z'));
const timestamp=s=>date(s).toLocaleString();
const delivery=s=>s==='sent'?'Sent to printer':s==='not_configured'?'Not configured':'Delivery uncertain/failed';
const fresh=()=>({table_id:'',takeaway:false,customer:'',items:[],notes:'',key:crypto.randomUUID()});
export default function WaiterWorkspace({page}){
 const [params]=useSearchParams(),navigate=useNavigate(),{user}=useAuth();
 const billId=params.get('bill'),editing=page==='new-order',history=page==='history';
 const query=useLive(billId?'/api/orders/'+billId:'/api/orders?active='+!history+'&sort=oldest&limit=100&offset='+Number(params.get('offset')||0));
 const tables=useLive('/api/tables'),menu=useLive('/api/menu');
 const storage='b360_waiter_drafts:'+user.id+':'+(billId||'new');
 const [draft,setDraft]=useState(()=>{try{return JSON.parse(localStorage.getItem(storage))||fresh()}catch{return fresh()}});
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [kind,setKind]=useState('remove'),[reason,setReason]=useState(''),[reductions,setReductions]=useState({});
 const [,tick]=useState(0);useEffect(()=>{const timer=setInterval(()=>tick(n=>n+1),60000);return()=>clearInterval(timer)},[]);
 useEffect(()=>{if(editing)localStorage.setItem(storage,JSON.stringify(draft))},[draft,storage,editing]);
 const update=values=>setDraft(d=>({...d,...values}));
 const change=(id,quantity)=>update({items:[...draft.items.filter(i=>i.menu_item_id!==id),...(quantity>0?[{menu_item_id:id,quantity}]:[])]});
 const [billSearch,setBillSearch]=useState(''),[billDay,setBillDay]=useState('');
 const visibleBills=Array.isArray(query.data)?query.data.filter(o=>JSON.stringify([o.order_number,o.table_number,o.items]).toLowerCase().includes(billSearch.toLowerCase())&&(!billDay||date(o.created_at).toLocaleDateString('en-CA',{timeZone:'Africa/Nairobi'})===billDay)):[];
 const bill=billId?query.data:null;
 async function submit(e,expectedVersion){e.preventDefault();if(busy)return;setBusy(true);setError('');
 const payload=draft.pending||{...(billId?{expected_version:expectedVersion??bill.version}:draft.takeaway?{order_type:'takeaway',customer:draft.customer?.trim()||null}:{table_id:Number(draft.table_id)}),items:draft.items,notes:draft.notes};
 update({pending:payload});
 try{const result=await request(billId?'/api/orders/'+billId+'/items':'/api/orders',{method:'POST',headers:{'Idempotency-Key':draft.key},body:JSON.stringify(payload)});
 localStorage.removeItem(storage);navigate('/waiter/bills?bill='+result.id);
 }catch(e){setError(e.message);if(e.status&&e.status<500){update({pending:null,key:crypto.randomUUID()});query.reload();tables.reload();menu.reload()}}
 finally{setBusy(false)}
 }
 async function requestChange(e){e.preventDefault();setBusy(true);setError('');
 try{await http.post('/api/orders/'+bill.id+'/change-requests',{expected_version:bill.version,kind,reason,items:kind==='cancel'?[]:Object.entries(reductions).filter(([,q])=>Number(q)>0).map(([id,q])=>({order_item_id:Number(id),quantity:Number(q)}))});setReason('');setReductions({});query.reload()}catch(e){setError(e.message);query.reload()}finally{setBusy(false)}
 }
 return <div className="waiter-workspace"><div className="waiter-heading"><div><h1>{editing?(billId?'Add items':'New order'):billId?'Bill '+(bill?.order_number||''):history?'History':'My open bills'}</h1><p>{editing?'Review your items before sending.':'Your bills, oldest first. Updated every 15 seconds.'}</p></div>{!editing&&<Link className="btn primary" to="/waiter/new-order">New order</Link>}</div>
 {error&&<p role="alert">{error}</p>}<LiveState query={query}/>
 {!editing&&!billId&&query.data&&<><div className="live-actions"><Field label="Search bills on this page"><input type="search" value={billSearch} onChange={e=>setBillSearch(e.target.value)} placeholder="Order, table or food"/></Field>{history&&<Field label="Bill date on this page"><input type="date" value={billDay} onChange={e=>setBillDay(e.target.value)}/></Field>}<button className="btn" onClick={()=>{setBillSearch('');setBillDay('')}}>Clear filters</button></div>{query.data.length>0&&!visibleBills.length&&<p role="status">No bills match these filters on this page.</p>}<div className="bill-grid">{visibleBills.map(o=><Link className="bill-card" key={o.id} to={'/waiter/bills?bill='+o.id}><div className="live-actions"><strong>{o.table_number?'Table '+o.table_number:'Unassigned'}</strong><span>{o.order_number}</span></div><p>Opened {timestamp(o.created_at)} · {Math.max(0,Math.floor((Date.now()-date(o.created_at))/60000))} min</p><ul>{o.items.map(i=><li key={i.id}>{productImage({...menu.data?.find(m=>m.id===i.menu_item_id),name:i.name})&&<FoodPhoto className="bill-item-photo" src={productImage({...menu.data?.find(m=>m.id===i.menu_item_id),name:i.name})}/>}<span>{i.quantity} {String.fromCharCode(215)} {i.name}</span></li>)}</ul><strong>{money(o.total)}</strong><p>{o.locked?'Locked · '+o.status:'Submitted'} {o.payment_block_reason}</p>{o.batches?.flatMap(b=>b.deliveries.map(d=><small key={b.id+':'+d.department_id}>{d.department}: {delivery(d.status)}<br/></small>))}</Link>)}</div>{!query.data.length&&<Panel title={history?'No past bills':'No open bills'}><p>{history?'Completed and cancelled bills appear here.':'Choose New order to open a table bill.'}</p></Panel>}<div className="live-actions"><Link className="btn" to={'/waiter/'+(history?'history':'bills')+'?offset='+Math.max(0,Number(params.get('offset')||0)-100)}>Previous</Link>{query.data.length===100&&<Link className="btn" to={'/waiter/'+(history?'history':'bills')+'?offset='+(Number(params.get('offset')||0)+100)}>Next</Link>}</div></>}
 {!editing&&bill&&<><Panel title={(bill.table_number?'Table '+bill.table_number:bill.order_type==='takeaway'?'Takeaway'+(bill.customer?' · '+bill.customer:''):'Unassigned')+' · '+money(bill.total)}><p>Opened {timestamp(bill.created_at)} · {bill.locked?'Locked':'Submitted'}</p>{bill.addition_block_reason?<p>{bill.addition_block_reason}</p>:<Link className="btn primary" to={'/waiter/new-order?bill='+bill.id}>Add items</Link>}<TaxSummary summary={bill.tax_summary}/><p>{bill.payment_block_reason}</p><ul>{bill.items.map(i=><li key={i.id}>{i.quantity} × {i.name} — {money(i.subtotal)} {i.voided_quantity>0&&'('+i.voided_quantity+' voided)'}</li>)}</ul></Panel>
 {(bill.batches?.length?bill.batches:[{id:'legacy',kind:'Original legacy order',created_at:bill.created_at,items:bill.items,deliveries:[]}]).map(b=><Panel key={b.id} title={b.kind+' · '+timestamp(b.created_at)}><ul>{b.items.map((i,n)=><li key={n}>{i.quantity} × {i.name} — {money(Math.abs(i.quantity)*(i.unit_price??i.price_at_time??0))}</li>)}</ul><p>{b.notes}</p>{b.deliveries.map(d=><p key={d.department_id}>{d.department}: {delivery(d.status)}</p>)}</Panel>)}
 {bill.change_requests?.map(r=><p key={r.id}>{r.kind}: {r.reason} — {r.status}{r.decision_reason&&' · '+r.decision_reason}</p>)}
 {!bill.locked&&<Panel title="Request a bill change"><form onSubmit={requestChange}><fieldset disabled={busy}><Field label="Change type"><select value={kind} onChange={e=>setKind(e.target.value)}><option value="remove">Reduce quantities</option><option value="cancel">Cancel entire bill</option></select></Field>{kind==='remove'&&bill.items.filter(i=>i.quantity>0).map(i=><Field key={i.id} label={'Remove '+i.name+' (remaining '+i.quantity+')'}><input type="number" min="0" max={i.quantity} value={reductions[i.id]||0} onChange={e=>setReductions({...reductions,[i.id]:e.target.value})}/></Field>)}<Field label="Reason"><textarea required minLength={3} value={reason} onChange={e=>setReason(e.target.value)}/></Field><p>The bill changes only after manager or director approval.</p><button className="btn" type="submit">Request approval</button></fieldset></form></Panel>}</>}
 {editing&&<WaiterOrderComposer bill={bill} billId={billId} user={user} tables={tables} menu={menu} draft={draft} update={update} change={change} busy={busy} error={error} submit={submit} LiveState={LiveState}/>}
 </div>;
}
