import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {ReceiptText,Search,Wallet,Smartphone,RefreshCw,CheckCircle2,Clock3} from 'lucide-react';
import {useAuth} from '../auth/AuthContext';
import {useLive,LiveState} from './WaiterWorkspace';
import {money,Field} from './LiveUI';
import TaxSummary from '../components/TaxSummary';
import {Receipt} from './LiveOrders';
import {retryablePost} from '../services/retryableWrite';
import {http} from '../services/http';
import MpesaPrompt,{useMpesaEnabled} from '../components/MpesaPrompt';
import './cashier-checkout.css';

const statusLabel={pending:'New bill',printed:'Preparing',ready:'Ready',payment_pending:'Awaiting confirmation',cleared:'Paid',completed:'Paid',cancelled:'Cancelled'};
const closed=order=>['cleared','completed','cancelled'].includes(order.status);
function age(value){if(!value)return 'Just opened';const timestamp=Date.parse(/[Z+]/.test(value)?value:value+'Z');if(!Number.isFinite(timestamp))return '';const mins=Math.max(0,Math.floor((Date.now()-timestamp)/60000));return mins<60?mins+' min':Math.floor(mins/60)+'h '+mins%60+'m'}

export default function CashierCheckout(){
 const {user}=useAuth(),[offset,setOffset]=useState(0),[search,setSearch]=useState(''),[filter,setFilter]=useState('all'),[selected,setSelected]=useState(null),[receipt,setReceipt]=useState(null);
 const queue=useLive('/api/orders?active=true&sort=oldest&limit=100&offset='+offset),shifts=useLive('/api/cashier/shifts');
 const rows=(queue.data||[]).filter(o=>!closed(o));
 const payable=o=>!o.locked&&!o.payment_block_reason&&o.status!=='payment_pending';
 const visible=rows.filter(o=>(filter==='all'||(filter==='payable'?payable(o):o.status==='payment_pending'))&&[o.order_number,o.table_number,o.waiter,o.customer].join(' ').toLowerCase().includes(search.toLowerCase()));
 const shift=Array.isArray(shifts.data)?shifts.data.find(s=>s.cashier_id===user.id&&s.status==='open'):null;
 const refresh=()=>{queue.reload();shifts.reload()};
 function settled(value){setReceipt(value);setSelected(null);refresh()}
 return <div className="cashier-checkout">
  <div className="cashier-title"><div><span className="cashier-eyebrow">PAYMENTS & CHECKOUT</span><h1>Cashier Station</h1><p>Select a bill, check the total, record payment.</p></div><button className="btn" onClick={refresh}><RefreshCw size={16}/>Refresh</button></div>
  <div className="cashier-shift"><div><span className={'cashier-dot '+(shift?'is-open':'')}/><strong>{shifts.error?'Shift status unavailable':!shifts.data?'Checking shift…':shift?'Shift #'+shift.id+' open':'No open shift'}</strong><span>{user.full_name||user.username}</span></div><Link to={'/'+user.role+'/reconciliation'}>{shift?'Shift details':'Open / check shift'} →</Link></div>
  <div className="cashier-counters"><div><span>Bills on this page</span><strong>{queue.data?rows.length:'—'}</strong></div><div><span>Available to pay</span><strong>{queue.data?rows.filter(payable).length:'—'}</strong></div><div><span>Awaiting confirmation</span><strong>{queue.data?rows.filter(o=>o.status==='payment_pending').length:'—'}</strong></div><div><span>Drawer expected</span><strong>{shift?money(shift.expected_cash):'—'}</strong></div></div>
  {receipt&&<section className="cashier-complete" aria-live="polite"><div><CheckCircle2/><strong>{receipt.status==='completed'?'Payment recorded':'Cashless entry recorded — confirmation required'}</strong><button className="btn" onClick={()=>setReceipt(null)}>Next bill</button></div><Receipt receipt={receipt}/>{receipt.status==='pending'&&<Link className="btn" to={'/'+user.role+'/mpesa'}>Open cashless confirmations</Link>}</section>}
  <div className={'cashier-workbench '+(selected?'has-selection':'')}>
   <section className="cashier-queue" aria-label="Bill queue"><div className="cashier-section-heading"><h2>Bill queue</h2><span>Oldest first</span></div>
    <label className="cashier-search"><Search size={17}/><input aria-label="Search bills on this page" placeholder="Table, bill or waiter" value={search} onChange={e=>setSearch(e.target.value)}/></label>
    <div className="cashier-filters" aria-label="Bill filters">{[['all','All'],['payable','To pay'],['pending','Cashless']].map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}</button>)}</div>
    <LiveState query={queue}/><div className="cashier-queue-list">{visible.map(o=><button className={'cashier-bill '+(selected?.id===o.id?'selected':'')} key={o.id} aria-pressed={selected?.id===o.id} onClick={()=>{setSelected({id:o.id,version:o.version});setReceipt(null)}}><span className="cashier-bill-top"><strong>{o.table_number?'Table '+o.table_number:o.order_number}</strong><b>{money(o.total)}</b></span><span className="cashier-bill-ref">{o.order_number} · {o.waiter}</span><span className="cashier-bill-bottom"><span className={'cashier-status '+(o.payment_block_reason?'hold':o.status)}>{o.payment_block_reason?'Approval needed':statusLabel[o.status]||o.status}</span><span><Clock3 size={12}/>{age(o.created_at)}</span></span></button>)}</div>
    {queue.data&&!visible.length&&<div className="cashier-empty-small"><ReceiptText/><strong>{rows.length?'No matching bills':'No open bills on this page'}</strong><p>{rows.length?'Try another table or clear the filters.':'New waiter bills appear automatically.'}</p>{(search||filter!=='all')&&<button className="btn" onClick={()=>{setSearch('');setFilter('all')}}>Clear filters</button>}</div>}
    <div className="cashier-pagination"><button className="btn" disabled={!offset} onClick={()=>setOffset(n=>Math.max(0,n-100))}>Previous</button><span>Page {offset/100+1}</span><button className="btn" disabled={(queue.data||[]).length<100} onClick={()=>setOffset(n=>n+100)}>Next</button></div>
   </section>
   {selected?<SelectedBill key={selected.id} identity={selected} onClose={()=>setSelected(null)} onSettled={settled}/>:<section className="cashier-welcome"><div className="cashier-welcome-icon"><ReceiptText size={30}/></div><h2>Ready for the next bill</h2><p>Choose a table from the queue to see its items and payment options.</p><div><span>1 · Select bill</span><span>2 · Check items</span><span>3 · Record payment</span></div><small>Prices include VAT. Cashless entries require manual confirmation.</small></section>}
  </div>
 </div>;
}

function SelectedBill({identity,onClose,onSettled}){
 const {user}=useAuth(),query=useLive('/api/orders/'+identity.id),bill=query.data;
 const [reviewedVersion,setReviewedVersion]=useState(identity.version),[method,setMethod]=useState('cash'),[tender,setTender]=useState(''),[reference,setReference]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState(null);
 const previousVersion=useRef(null),mpesaEnabled=useMpesaEnabled();
 useEffect(()=>{if(bill){if(previousVersion.current!==null&&previousVersion.current!==bill.version){setTender('');setReference('')}previousVersion.current=bill.version}},[bill]);
 const changed=bill&&bill.version!==reviewedVersion;
 const blocked=!bill?'Loading bill details…':query.error?'Reconnect and refresh this bill before paying.':closed(bill)?'This bill is already closed.':bill.payment_block_reason||((bill.locked||bill.status==='payment_pending')?'Payment already recorded. Check the payment ledger.':changed?'This bill changed. Review the updated items and total before continuing.':'');
 const amount=bill?.total||0,received=tender===''?amount:Number(tender),change=Math.round((received-amount)*100)/100;
 async function promptPaid(){
  // The server cleared the bill when M-Pesa confirmed it; show its receipt.
  try{const rows=await http.get('/api/payments?limit=100');const payment=rows.find(p=>p.order_id===identity.id&&p.status==='completed');
   if(payment)return onSettled({...payment,items:payment.snapshot?.items||bill.items,tax_summary:payment.snapshot?.tax_summary||bill.tax_summary})}
  catch{/* fall through to a refresh */}
  query.reload();
 }
 async function pay(e){e.preventDefault();if(busy||(!pending&&blocked))return;setBusy(true);setError('');const submission=pending||{expected_version:bill.version,amount:bill.total,method,reference:method==='m-pesa'?reference.trim():null,tendered_amount:method==='cash'?received:null};setPending(submission);
  try{const result=await retryablePost('/api/orders/'+identity.id+'/clear',submission);setPending(null);onSettled({...result,items:result.snapshot?.items||bill.items,tax_summary:result.snapshot?.tax_summary||bill.tax_summary})}
  catch(e){setError(e.message);if(e.status&&e.status<500){setPending(null);query.reload()}}
  finally{setBusy(false)}
 }
 return <><section className="cashier-detail" aria-label="Selected bill"><div className="cashier-section-heading"><div><span className="cashier-eyebrow">SELECTED BILL</span><h2>{bill?.table_number?'Table '+bill.table_number:'Bill details'}</h2></div><button className="btn" disabled={busy||!!pending} onClick={onClose}>Back to bills</button></div><LiveState query={query}/>{bill&&<><div className="cashier-detail-meta"><strong>{bill.order_number}</strong><span>{bill.waiter} · {statusLabel[bill.status]||bill.status}</span></div><div className="cashier-item-head"><span>Item / quantity</span><span>Amount</span></div><ul className="cashier-items">{bill.items.filter(i=>i.quantity>0).map(i=><li key={i.id}><span className="cashier-item-quantity">{i.quantity}×</span><div><strong>{i.name}</strong>{i.unit_price!=null&&<small>{money(i.unit_price)} each</small>}</div><b>{money(i.subtotal)}</b></li>)}</ul><div className="cashier-bill-total"><span>Bill total</span><strong>{money(amount)}</strong></div><TaxSummary summary={bill.tax_summary}/>{changed&&!pending&&<div className="cashier-warning" role="status"><p>This bill has changed since it was selected.</p><button className="btn" onClick={()=>setReviewedVersion(bill.version)}>I reviewed the updated bill</button></div>}</>}</section>
  <section className="cashier-payment" aria-label="Payment"><span className="cashier-eyebrow">PAYMENT</span><div className="cashier-due"><span>Amount due</span><strong>{bill?money(amount):'—'}</strong><small>VAT included</small></div>{blocked&&<p className="cashier-warning" role="status">{blocked}</p>}{bill?.status==='payment_pending'&&<Link className="btn" to={'/'+user.role+'/payment-ledger'}>Check recorded payment</Link>}
   <form onSubmit={pay}><fieldset disabled={busy||!!pending||!!blocked}><div className="cashier-methods" aria-label="Payment method">{[['cash','Cash',Wallet],['m-pesa','M-Pesa',Smartphone]].map(([id,label,Icon])=><button key={id} type="button" aria-pressed={method===id} onClick={()=>{setMethod(id);setReference('')}}><Icon size={19}/>{label}</button>)}</div>
    {method==='cash'?<><Field label="Cash received (KES)"><input type="number" inputMode="decimal" step="0.01" min={amount} value={tender} placeholder={String(amount)} onChange={e=>setTender(e.target.value)}/></Field><div className="cashier-quick-cash">{[amount,...[500,1000,2000].filter(v=>v>amount)].map((v,i)=><button key={v} className="btn" type="button" onClick={()=>setTender(String(v))}>{i===0?'Exact':money(v)}</button>)}</div><div className={'cashier-change '+(change<0?'short':'')}><span>{change<0?'Still needed':'Change to return'}</span><strong>{money(Math.abs(change))}</strong></div></>:<>{mpesaEnabled&&bill&&<><MpesaPrompt target={{order_id:identity.id,expected_version:bill.version}} amount={amount} disabled={!!blocked} onPaid={promptPaid}/><p className="cashier-payment-help">Or, if the customer already paid to the business number, enter the receipt from their message:</p></>}<Field label="Payment reference"><input required={!mpesaEnabled} maxLength={100} autoComplete="off" placeholder="Enter external receipt reference" value={reference} onChange={e=>setReference(e.target.value)}/></Field><p className="cashier-payment-help">Record the reference received from the customer. This entry stays pending until the external receipt is verified.</p></>}
   </fieldset>{error&&<p role="alert" className="cashier-warning">{error}</p>}{pending&&!busy&&<p role="status">The response was not confirmed. Retry this payment to check the original submission safely.</p>}<button className="btn primary cashier-pay-button" disabled={busy||(!pending&&(!!blocked||(method==='cash'&&received<amount)||(method==='m-pesa'&&!reference.trim())))}>{busy?'Recording…':pending?'Retry payment':method==='cash'?'Record cash payment':'Record cashless payment'}</button><p className="cashier-payment-help">{method==='cash'?'Confirm only after receiving the cash.':'No money is transferred by this button.'}</p></form>
  </section></>;
}
