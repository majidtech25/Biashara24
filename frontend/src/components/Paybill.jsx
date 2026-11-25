import {useCallback,useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {Printer} from 'lucide-react';
import {http} from '../services/http';
import {money} from '../pages/LiveUI';
import TaxSummary from './TaxSummary';
import '../pages/cashier-payments.css';

const REFRESH_MS=10000;

/** Paybill number, account number, QR code and payments received for a bill or car wash. */
export function usePaybill(target){
 const key=target.order_id?'order_id='+target.order_id:'carwash_id='+target.carwash_id;
 const [details,setDetails]=useState(null),[error,setError]=useState('');
 const load=useCallback(()=>http.get('/api/paybill/bill?'+key).then(d=>{setDetails(d);setError('')}).catch(e=>setError(e.message)),[key]);
 useEffect(()=>{load();const timer=setInterval(load,REFRESH_MS);return()=>clearInterval(timer)},[load]);
 return {details,error,reload:load};
}

/** How to pay by M-Pesa, as printed on the bill. */
export function PaybillBlock({details}){
 if(!details?.paybill)return null;
 return <section className="paybill-block" aria-label="Pay with M-Pesa">
  <strong>Pay with M-Pesa</strong>
  <dl><div><dt>Paybill</dt><dd>{details.paybill}</dd></div><div><dt>Account</dt><dd>{details.account}</dd></div><div><dt>Amount</dt><dd>{money(details.amount)}</dd></div></dl>
  {details.qr?<><img src={'data:image/png;base64,'+details.qr} alt="M-Pesa QR code for this bill" width="160" height="160"/><small>Scan with the M-PESA or My Safaricom app</small></>:details.qr_note&&<small className="muted">{details.qr_note}</small>}
 </section>;
}

/** The customer's bill before payment, with Paybill details and QR code, ready to print. */
export function CustomerBill({bill,details}){
 const [business,setBusiness]=useState(null);
 useEffect(()=>{http.get('/api/settings').then(setBusiness).catch(()=>setBusiness(null))},[]);
 const paper=<article className="receipt-paper" aria-label="Customer bill">
  <header><span className="receipt-mark">BILL</span><h2>{business?.business_name||'Biashara360'}</h2>{business?.address&&<p>{business.address}</p>}{business?.phone&&<p>{business.phone}</p>}<strong className="payment-status pending">NOT YET PAID</strong></header>
  <dl className="payment-facts"><div><dt>Bill</dt><dd>{bill.order_number}</dd></div>{bill.table_number&&<div><dt>Table</dt><dd>{bill.table_number}</dd></div>}{bill.waiter&&<div><dt>Served by</dt><dd>{bill.waiter}</dd></div>}</dl>
  <ul className="receipt-lines">{bill.items.filter(i=>i.quantity>0).map((i,n)=><li key={i.id??n}><span>{i.quantity} × {i.name}</span><strong>{money(i.subtotal)}</strong></li>)}</ul>
  <TaxSummary summary={bill.tax_summary}/><div className="receipt-total"><span>Total to pay</span><strong>{money(bill.total)}</strong></div>
  <PaybillBlock details={details}/>
  <footer>Pay by cash at the counter or by M-Pesa above, then show your M-Pesa message to the cashier.</footer>
 </article>;
 return <>{<button type="button" className="btn" onClick={()=>window.print()}><Printer size={16}/>Print bill</button>}{createPortal(<div className="receipt-print-root" aria-hidden="true">{paper}</div>,document.body)}</>;
}

/** Payments Safaricom reported for this bill or car wash. "Use" puts the receipt in the form. */
export function PaymentsReceived({details,onUse,selected}){
 const rows=details?.payments||[];
 if(!details?.paybill)return null;
 return <div className="paybill-received" role="region" aria-label="M-Pesa payments received">
  <strong>M-Pesa payments received for this {details.account?'account':'bill'}</strong>
  {!rows.length?<p className="muted">None yet. This list updates by itself. The customer pays to Paybill {details.paybill}, account {details.account}.</p>:
  <ul>{rows.map(p=><li key={p.id} className={p.status}><span><b>{p.receipt}</b> · {money(p.amount)} · {p.payer||p.phone||'Customer'}</span>{p.status==='used'?<em>Already used</em>:<button type="button" className="btn" aria-pressed={selected===p.receipt} onClick={()=>onUse(p)}>{selected===p.receipt?'Selected':'Use this payment'}</button>}</li>)}</ul>}
 </div>;
}

/** Managers: today's Paybill payments, with those not yet used by staff first. */
export function PaybillFeed(){
 const [rows,setRows]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let live=true;const load=()=>http.get('/api/paybill/payments').then(r=>live&&setRows(r)).catch(e=>live&&setError(e.message));load();const t=setInterval(load,30000);return()=>{live=false;clearInterval(t)}},[]);
 if(error)return <p role="alert">{error}</p>;
 if(!rows?.length)return null;
 const waiting=rows.filter(r=>r.status==='received');
 return <section className="panel paybill-feed" aria-label="M-Pesa Paybill payments"><h2>M-Pesa Paybill payments</h2>
  <p>{waiting.length?`${waiting.length} payment${waiting.length>1?'s':''} received but not yet confirmed by staff. A payment with no matching bill usually means the customer typed the account number wrongly.`:'Every payment received has been confirmed by staff.'}</p>
  <div className="table-scroll"><table><thead><tr><th>Receipt</th><th>Amount</th><th>Account typed</th><th>Payer</th><th>Matched to</th><th>Status</th></tr></thead>
  <tbody>{[...waiting,...rows.filter(r=>r.status!=='received')].map(r=><tr key={r.id}><td>{r.receipt}</td><td>{money(r.amount)}</td><td>{r.account||'—'}</td><td>{r.payer||r.phone||'—'}</td><td>{r.order_id?'Bill #'+r.order_id:r.carwash_id?'Car wash #'+r.carwash_id:'No match'}</td><td>{r.status==='used'?'Confirmed':'Waiting for staff'}</td></tr>)}</tbody></table></div>
 </section>;
}
