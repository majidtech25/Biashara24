import {useEffect,useId,useRef,useState} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {Search,ShoppingBag,UtensilsCrossed,Plus,Minus,X,ArrowLeft,Check} from 'lucide-react';
import {money,Field} from './LiveUI';
import FoodPhoto from '../components/FoodPhoto';
import {productImage} from '../services/productImages';
import TaxSummary,{estimateTax} from '../components/TaxSummary';

export default function WaiterOrderComposer({bill,billId,user,tables,menu,draft,update,change,busy,error,submit,LiveState}){
 const navigate=useNavigate(),dialog=useRef(null);
 const [search,setSearch]=useState(''),[category,setCategory]=useState(''),[sheet,setSheet]=useState(null);
 const [reviewVersion,setReviewVersion]=useState(null),[choosingTable,setChoosingTable]=useState(false);
 const takeaway=!billId&&!!draft.takeaway;
 const selectedTable=takeaway?null:tables.data?.find(t=>t.id===Number(draft.table_id));
 const tableNumber=billId?bill?.table_number:selectedTable?.number;
 const tableLabel=takeaway||(billId&&bill?.order_type==='takeaway')?'Takeaway'+((takeaway?draft.customer:bill?.customer)?' · '+(takeaway?draft.customer:bill.customer):''):tableNumber?'Table '+tableNumber:billId?'Unassigned':'Choose a table';
 const cart=draft.items.map(i=>({...i,menu:(()=>{const item=menu.data?.find(m=>m.id===i.menu_item_id);return item?{...item,image:productImage(item)}:undefined})()}));
 const count=cart.reduce((n,i)=>n+i.quantity,0);
 const subtotal=cart.reduce((n,i)=>n+(i.menu?.price||0)*i.quantity,0);
 const total=subtotal+(billId?bill?.total||0:0);
 const cartTax=estimateTax(cart.map(i=>({price:i.menu?.price||0,quantity:i.quantity})));
 const taxSummary=!billId?cartTax:bill?.tax_summary?{tax_amount:Math.round((bill.tax_summary.tax_amount+cartTax.tax_amount)*100)/100,net_amount:Math.round((bill.tax_summary.net_amount+cartTax.net_amount)*100)/100}:null;
 const frozen=busy||!!draft.pending;
 const reviewHelpId=useId();
 const reviewBlock=busy?'Your order is being sent. Please wait.'
  :draft.pending?'The last submission has not been confirmed. Use Retry submission below before starting another.'
  :menu.error?'The menu could not be refreshed. Retry the connection before reviewing.'
  :!menu.data?'Loading the menu. Please wait.'
  :!billId&&!takeaway&&tables.error?'Tables could not be refreshed. Retry the connection before reviewing.'
  :!billId&&!takeaway&&!tables.data?'Loading tables. Please wait.'
  :!billId&&!takeaway&&!tables.data?.some(t=>t.is_active)?'No active tables are configured. Ask your manager to add or activate a table.'
  :!billId&&!takeaway&&!selectedTable?'Select an available table before reviewing your order.'
  :!billId&&!takeaway&&!selectedTable.is_active?'The selected table is inactive. Choose another table.'
  :!billId&&!takeaway&&selectedTable.occupied?(selectedTable.mine?'This table already has your bill. Open that bill to add these items.':'This table is now occupied. Choose another available table.')
  :billId&&!bill?'Loading the bill. Please wait.'
  :billId&&(bill.locked||bill.addition_block_reason)?bill.addition_block_reason||'This bill is locked and cannot accept more items.'
  :!cart.length?'Add at least one food or drink before reviewing your order.'
  :cart.some(i=>!i.menu)?'An item in your cart is no longer available. Remove it or choose another item.'
  :cart.some(i=>!Number.isInteger(i.quantity)||i.quantity<1||i.quantity>100)?'Item quantities must be whole numbers from 1 to 100.'
  :'';
 const valid=!reviewBlock;
 const visible=(menu.data||[]).map(m=>({...m,image:productImage(m)})).filter(m=>(!category||m.category===category)&&m.name.toLowerCase().includes(search.toLowerCase()));
 const categories=[...new Set((menu.data||[]).map(m=>m.category).filter(Boolean))];
 useEffect(()=>{
  if(sheet&&!dialog.current?.open){dialog.current?.showModal()}else if(!sheet&&dialog.current?.open){dialog.current.close()}
 },[sheet]);
 useEffect(()=>{if(!busy&&(error||draft.pending))setSheet(null)},[busy,error,draft.pending]);
 function review(){if(!valid||frozen)return;setReviewVersion(bill?.version);setSheet('review')}
 async function confirm(e){await submit(e,reviewVersion)}
 const quantityControls=(item,quantity,location='')=><div className="quantity-controls">
  <button type="button" className="btn" aria-label={'Remove one '+item.name+location} disabled={frozen||!quantity} onClick={()=>change(item.id,quantity-1)}><Minus size={18}/></button>
  <output aria-label={item.name+' quantity'+location}>{quantity}</output>
  <button type="button" className="btn" aria-label={'Add one '+item.name+location} disabled={frozen||quantity>=100} onClick={()=>change(item.id,quantity+1)}><Plus size={18}/></button>
 </div>;
 const cartContents=()=> <>
  <div className="order-cart-heading"><div><small>{billId?'NEW ITEMS ONLY':'CURRENT ORDER'}</small><h2>{billId?'Addition cart':'Your order'}</h2></div><span className="item-count">{count}</span></div>
  <p className="cart-table-label">{tableLabel}</p>
  {!cart.length&&<div className="cart-empty"><ShoppingBag size={36}/><h3>Your cart is empty</h3><p>Find an item on the menu and tap Add.</p></div>}
  <div className="cart-lines">{cart.map(i=><div className="cart-line" key={i.menu_item_id}>{i.menu?.image&&<FoodPhoto className="cart-food-photo" src={i.menu.image}/>}<div className="cart-line-title"><strong>{i.menu?.name||'Unavailable item'}</strong><strong>{money((i.menu?.price||0)*i.quantity)}</strong></div><small>{money(i.menu?.price||0)} each</small><div className="cart-line-controls">{quantityControls({id:i.menu_item_id,name:i.menu?.name||'Unavailable item'},i.quantity,' in cart')}<button type="button" className="cart-remove" disabled={frozen} aria-label={'Remove '+(i.menu?.name||'unavailable item')+' from cart'} onClick={()=>change(i.menu_item_id,0)}>Remove</button></div></div>)}</div>
  <Field label="Kitchen notes"><textarea disabled={frozen} placeholder="For example: no sugar, sauce on the side" maxLength={1000} value={draft.notes} onChange={e=>update({notes:e.target.value})}/></Field>
  <div className="cart-totals">{billId&&<><p>Current bill: {money(bill?.total||0)}</p><p>Additional items: {money(subtotal)}</p></>}<strong>Estimated {billId?'revised ':''}total: {money(total)}</strong><TaxSummary summary={taxSummary}/><small>Prices include 16% VAT and are confirmed when your items are accepted.</small></div>
  {bill?.addition_block_reason&&<p role="status">{bill.addition_block_reason}</p>}
  {!billId&&!takeaway&&!selectedTable&&<p className="cart-help">Choose a table to continue.</p>}{takeaway&&!frozen&&<><Field label="Customer name (optional)"><input maxLength={120} value={draft.customer||''} onChange={e=>update({customer:e.target.value})}/></Field><button className="btn" type="button" onClick={()=>update({takeaway:false,customer:''})}>Serve at a table instead</button></>}
  {reviewBlock&&<p id={reviewHelpId} className="cart-help" role="status">{reviewBlock}</p>}
  {!billId&&selectedTable&&(!selectedTable.is_active||selectedTable.occupied)&&!frozen&&<button className="btn" type="button" onClick={()=>{setSheet(null);setChoosingTable(true)}}>Choose another table</button>}
  {!billId&&selectedTable?.mine&&selectedTable.order_id&&<Link className="btn" to={'/waiter/new-order?bill='+selectedTable.order_id}>Add to existing bill</Link>}
  <button className="btn primary review-order" type="button" disabled={!valid||frozen} aria-describedby={reviewBlock?reviewHelpId:undefined} onClick={review}>Review {billId?'addition':'order'} <Check size={18}/></button>
  <p className="cart-help">Unsent items can be removed here. Submitted items need manager approval.</p>
 </>;
 return <div className="waiter-ordering">
  <div className="order-context"><div className="order-context-table"><UtensilsCrossed size={22}/><div><strong>{tableLabel}</strong><small>{billId?'Adding to '+(bill?.order_number||'existing bill'):'New bill'}</small></div></div><div className="order-context-owner"><small>WAITER</small><strong>{user.full_name||user.username}</strong></div>{!billId&&selectedTable&&<button type="button" className="btn" disabled={frozen} onClick={()=>setChoosingTable(v=>!v)}>{choosingTable?'Hide tables':'Change table'}</button>}{billId&&<Link className="btn" to={'/waiter/bills?bill='+billId}>Back to bill</Link>}</div>
  <LiveState query={tables}/>
  {!billId&&!takeaway&&(!selectedTable||choosingTable)&&<section className="table-selection" aria-label="Choose a table"><div className="menu-section-heading"><h2>Select a table</h2><span>Tap a number to start</span></div><div className="table-picker"><button type="button" disabled={frozen} className="table-target takeaway-target" onClick={()=>{update({takeaway:true,table_id:''});setChoosingTable(false)}}><strong>Takeaway</strong><span>No table</span></button>{tables.data?.filter(t=>t.is_active).map(t=><button type="button" key={t.id} disabled={frozen||(t.occupied&&!t.mine)} aria-pressed={Number(draft.table_id)===t.id} className={'table-target '+(Number(draft.table_id)===t.id?'selected':'')} onClick={()=>{if(t.mine){navigate('/waiter/bills?bill='+t.order_id)}else{update({table_id:t.id});setChoosingTable(false)}}}><strong>Table {t.number}</strong><span>{t.mine?'Your bill - Open':t.occupied?'Occupied · '+t.owner:'Available'}</span></button>)}</div>{tables.data?.length===0&&<p>No tables configured. Ask your manager to add tables.</p>}</section>}
  <div className="waiter-compose">
   <section className="waiter-menu" aria-label="Food menu">
    <div className="menu-section-heading"><div><h2>Menu</h2></div><span>{visible.length} items</span></div>
    <label className="waiter-search"><Search size={22}/><input type="search" aria-label="Search menu" placeholder="Search food or drinks…" value={search} onChange={e=>setSearch(e.target.value)}/></label>
    <div className="menu-categories" role="group" aria-label="Menu categories">{['',...categories].map(c=><button key={c} type="button" aria-pressed={category===c} onClick={()=>setCategory(c)}>{c||'All items'}</button>)}</div>
    <LiveState query={menu}/>
    <div className="menu-grid">{visible.map(m=>{const quantity=draft.items.find(i=>i.menu_item_id===m.id)?.quantity||0;return <article className={'menu-tile '+(quantity?'has-items':'')} key={m.id}><div className="food-photo-wrap">{m.image?<FoodPhoto className="menu-food-photo" src={m.image} alt={m.name}/>:<div className="food-photo-placeholder"><UtensilsCrossed size={36}/></div>}{quantity>0&&<span className="menu-selected"><Check size={14}/> {quantity} in cart</span>}</div><div className="food-card-title"><h3>{m.name}</h3><p className="menu-price">{money(m.price)}</p></div>{quantity?quantityControls(m,quantity):<div className="menu-add-row"><output className="sr-only" aria-label={m.name+' quantity'}>0</output><button className="btn menu-add" type="button" disabled={frozen} aria-label={'Add one '+m.name} onClick={()=>change(m.id,1)}><Plus size={18}/> Add</button></div>}</article>})}</div>
    {menu.data&&!visible.length&&<div className="menu-empty"><h3>{menu.data.length?'No matching items':'No available menu items'}</h3><p>{menu.data.length?'Try another name or category.':'Ask your manager to update the menu.'}</p>{menu.data.length>0&&<button className="btn" type="button" onClick={()=>{setSearch('');setCategory('')}}>Clear filters</button>}</div>}
   </section>
   <aside className="order-cart" aria-label="Current order">{sheet!=='cart'&&cartContents()}</aside>
  </div>
  {draft.pending&&<div className="submission-retry" role="status"><strong>Submission not yet confirmed</strong><p>Your items are saved here. Retry the same submission to check it safely.</p><button className="btn primary" type="button" disabled={busy} onClick={submit}>{busy?'Sending…':'Retry submission'}</button></div>}
  {!sheet&&<button type="button" className="btn primary portrait-cart-button" aria-haspopup="dialog" onClick={()=>setSheet('cart')}><ShoppingBag size={22}/><span>View order · {count} {count===1?'item':'items'}</span><strong>{money(total)}</strong></button>}
  <dialog className="waiter-order-dialog" ref={dialog} onCancel={()=>setSheet(null)} onClose={()=>setSheet(null)} aria-labelledby="order-dialog-title">
   {sheet&&<><div className="order-dialog-heading"><h2 id="order-dialog-title">{sheet==='review'?(billId?'Review addition':'Review order'):'Current order'}</h2><button type="button" className="btn" aria-label="Close order" onClick={()=>setSheet(null)}><X size={22}/></button></div>
   {sheet==='cart'?cartContents():<><p className="review-context"><strong>{tableLabel}</strong> · {user.full_name||user.username}</p><p>{billId?'Only these additional items will be sent.':'Check the table and items before submitting.'}</p><ul className="review-lines">{cart.map(i=><li key={i.menu_item_id}><span>{i.quantity} × {i.menu?.name||'Unavailable item'}</span><strong>{money((i.menu?.price||0)*i.quantity)}</strong></li>)}</ul><div className="review-notes"><small>KITCHEN NOTES</small><p>{draft.notes||'No special instructions'}</p></div>{billId&&<p>Current bill: {money(bill?.total||0)}</p>}<p className="review-total">Estimated {billId?'revised ':''}total <strong>{money(total)}</strong></p><TaxSummary summary={taxSummary}/>{error&&<p role="alert">{error}</p>}<div className="review-actions"><button type="button" className="btn" disabled={frozen} onClick={()=>setSheet(null)}><ArrowLeft size={18}/> Edit order</button><button type="button" className="btn primary" disabled={!valid||frozen} onClick={confirm}>{busy?'Sending…':billId?'Send additional items':'Submit order'}</button></div>{draft.pending&&!busy&&<button className="btn primary" type="button" onClick={submit}>Retry submission</button>}</>}
   </>}
  </dialog>
 </div>;
}
