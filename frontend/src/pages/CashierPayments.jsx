import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {ReceiptText,RefreshCw,Download,Search} from 'lucide-react';
import {useLive,LiveState} from './WaiterWorkspace';
import {useAction,ActionFeedback,Field,money} from './LiveUI';
import {resourceService as api} from '../services/resourceService';
import {exportRows} from '../components/WorkspaceDialog';
import Receipt,{paymentDate} from './PaymentReceipt';
import './cashier-checkout.css';
import './cashier-payments.css';

const labels={pending:'Awaiting confirmation',completed:'Confirmed',rejected:'Rejected'};
export default function CashierPayments({page}){
 const receipts=page==='receipts',inspector=useRef(null);

 const [method,setMethod]=useState(page==='cash-payment'?'cash':page==='mpesa'?'m-pesa':''),[status,setStatus]=useState(receipts?'completed':page==='mpesa'?'pending':''),[search,setSearch]=useState(''),[from,setFrom]=useState(''),[to,setTo]=useState(''),[offset,setOffset]=useState(0),[selectedId,setSelectedId]=useState(null),[checked,setChecked]=useState(false);
 useEffect(()=>{if(selectedId!=null&&window.innerWidth<=1100)inspector.current?.scrollIntoView?.({block:'start',behavior:'smooth'})},[selectedId]);
 const params=new URLSearchParams({limit:'100',offset:String(offset),method,status_filter:status});if(from)params.set('from_date',from);if(to)params.set('to_date',to);
 const query=useLive('/api/payments?'+params);
 const refresh=()=>query.reload();
 const action=useAction(refresh),rows=query.data||[];
 const visible=rows.filter(p=>[p.receipt,p.order_number,p.reference,p.table_number].join(' ').toLowerCase().includes(search.toLowerCase()));
 const selected=rows.find(p=>p.id===selectedId);
 function filter(set,value){set(value);setOffset(0);setSelectedId(null);setChecked(false)}
 const title=receipts?'Receipts':page==='mpesa'?'M-Pesa confirmations':page==='cash-payment'?'Cash payments':'Payments';
 return <div className="cashier-checkout cashier-records">
  <div className="cashier-title"><div><span className="cashier-eyebrow">{receipts?'CUSTOMER RECEIPTS':'PAYMENT ACTIVITY'}</span><h1>{title}</h1><p>{receipts?'Find, review and print saved receipts.':'Track received payments and review cashless confirmations.'}</p></div><button className="btn" onClick={refresh}><RefreshCw size={16}/>Refresh</button></div>
  <nav className="payment-tabs" aria-label="Cashier payments"><Link to="/cashier/payment-ledger" aria-current={!receipts?'page':undefined}>M-Pesa to confirm</Link><Link to="/cashier/receipts" aria-current={receipts?'page':undefined}>Receipts</Link><Link to="/cashier/checkout">Go to checkout →</Link></nav>
  <section className="payment-filter-panel" aria-label="Transaction filters">
   <label className="field payment-search">Search this page<div className="cashier-search"><Search size={16}/><input type="search" aria-label="Search this page" placeholder="Receipt, bill, reference or table" value={search} onChange={e=>setSearch(e.target.value)}/></div></label>
   <Field label="Method"><select value={method} onChange={e=>filter(setMethod,e.target.value)}><option value="">All methods</option><option value="cash">Cash</option><option value="m-pesa">M-Pesa</option></select></Field>
   <Field label="Payment status"><select value={status} onChange={e=>filter(setStatus,e.target.value)}><option value="">All statuses</option><option value="completed">Confirmed</option><option value="pending">Awaiting confirmation</option><option value="rejected">Rejected</option></select></Field>
   <Field label="From date"><input type="date" max={to||undefined} value={from} onChange={e=>filter(setFrom,e.target.value)}/></Field><Field label="To date"><input type="date" min={from||undefined} value={to} onChange={e=>filter(setTo,e.target.value)}/></Field>
   <button className="btn" onClick={()=>{setMethod('');setStatus(receipts?'completed':'');setFrom('');setTo('');setSearch('');setOffset(0);setSelectedId(null);setChecked(false)}}>Reset filters</button>
  </section>
  <ActionFeedback action={action}/><div className="payment-workspace">
   <section className="payment-list" aria-label={receipts?'Receipt list':'Transaction list'}><div className="cashier-section-heading"><div><h2>{receipts?'Saved receipts':'Transactions'}</h2><small>{visible.length} on this page · Newest first</small></div><button className="btn payment-export" disabled={!visible.length||!!query.error} onClick={()=>exportRows('payments-current-page',[['receipt','Receipt'],['order_number','Bill'],['amount','Amount'],['method','Method'],['reference','Reference'],['status','Status']],visible)}><Download size={15}/>Export page</button></div>
    <LiveState query={query}/><div className="payment-list-head"><span>Bill / receipt</span><span>Payment</span><span>Amount</span></div>
    <div className="payment-rows">{visible.map(p=><button className={'payment-row '+(selectedId===p.id?'selected':'')} key={p.id} aria-pressed={selectedId===p.id} onClick={()=>{setSelectedId(p.id);setChecked(false)}}><span><strong>{receipts?p.receipt||p.order_number:p.order_number}</strong><small>{receipts?p.order_number:p.receipt||'No paid receipt'}{p.table_number?' · Table '+p.table_number:''}</small><small>{paymentDate(p.created_at)}</small></span><span><b>{p.method==='cash'?'Cash':'M-Pesa'}</b><small>{p.reference||'Cash received'}</small><span className={'payment-status '+p.status}>{labels[p.status]||p.status}</span></span><strong className="payment-row-amount">{money(p.amount)}<small>View {receipts?'receipt':'details'} →</small></strong></button>)}</div>
    {query.data&&!visible.length&&<div className="payment-empty"><ReceiptText size={28}/><h3>No matching {receipts?'receipts':'payments'}</h3><p>Try another date, method or search. Payments recorded at checkout appear here.</p></div>}
    <div className="cashier-pagination"><button className="btn" disabled={!offset} onClick={()=>{setOffset(n=>Math.max(0,n-100));setSelectedId(null)}}>Previous</button><span>Page {offset/100+1}</span><button className="btn" disabled={rows.length<100} onClick={()=>{setOffset(n=>n+100);setSelectedId(null)}}>Next</button></div>
   </section>
   <section ref={inspector} className="payment-inspector" aria-label={receipts?'Receipt preview':'Payment details'}>{selected?<>
    <div className="cashier-section-heading"><h2>{receipts?'Receipt preview':'Payment details'}</h2><button className="btn" onClick={()=>setSelectedId(null)}>Close details</button></div>
    {!receipts&&<><span className={'payment-status '+selected.status}>{labels[selected.status]}</span><div className="payment-inspector-amount">{money(selected.amount)}</div><dl className="payment-facts"><div><dt>Bill</dt><dd>{selected.order_number}</dd></div><div><dt>Method</dt><dd>{selected.method==='cash'?'Cash':'M-Pesa'}</dd></div><div><dt>Reference</dt><dd>{selected.reference||'—'}</dd></div><div><dt>Recorded</dt><dd>{paymentDate(selected.created_at)}</dd></div>{selected.completed_at&&<div><dt>Confirmed</dt><dd>{paymentDate(selected.completed_at)}</dd></div>}{selected.shift_id&&<div><dt>Shift</dt><dd>#{selected.shift_id}</dd></div>}</dl></>}
    {selected.status==='pending'&&<div className="payment-confirm"><h3>Check the external receipt</h3><p>Match <strong>{selected.reference}</strong> and <strong>{money(selected.amount)}</strong> against the business account before confirming.</p><label><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/>I checked the reference and amount.</label><button className="btn primary" disabled={!checked||action.busy||!!query.error} onClick={()=>action.run(async()=>{await api.verifyPayment(selected.id);setChecked(false)})}>{action.busy?'Confirming…':'Confirm external receipt'}</button></div>}
    {selected.status==='rejected'?<div className="cashier-warning"><strong>Rejected entry</strong><p>{selected.rejection_reason||'This entry was rejected. It is retained for the payment history.'}</p><p>No paid receipt is available.</p></div>:<Receipt receipt={selected}/>}
   </>:<div className="payment-empty"><ReceiptText size={34}/><h2>{receipts?'Select a receipt':'Select a transaction'}</h2><p>{receipts?'Review the saved items, VAT and payment details before printing.':'Choose a payment to see its reference, status and receipt.'}</p></div>}</section>
  </div>
 </div>;
}
