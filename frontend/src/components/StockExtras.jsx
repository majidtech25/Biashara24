import {useState} from 'react';
import {http} from '../services/http';
import WorkspaceDialog from './WorkspaceDialog';
import {useData,useAction,Feedback,ActionFeedback,Table,Field,money,Panel} from '../pages/LiveUI';

/** Stock batches that have expired or expire soon, soonest first. */
export function ExpiringStock(){
 const [days,setDays]=useState(7),query=useData('/api/stock/expiry?days='+days),rows=query.data||[];
 const expired=rows.filter(r=>r.status==='expired');
 return <Panel title="Expiring stock"><Field label="Show stock expiring within"><select value={days} onChange={e=>setDays(Number(e.target.value))}><option value={3}>3 days</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option></select></Field><Feedback query={query}/>
  {query.data&&(rows.length?<><p>{expired.length?`${expired.length} batch${expired.length>1?'es have':' has'} expired. Record it as ingredient wastage to remove it from stock.`:'Nothing has expired yet.'} Stock taken out is always taken from the batch that expires first.</p>
  <Table columns={[['ingredient','Ingredient'],['remaining','Left',(v,r)=>v+' '+(r?.unit||'')],['expiry_date','Expires'],['days_left','Days left',v=>v<0?'Expired '+(-v)+' day(s) ago':v===0?'Today':v],['value','Value at cost',money]]} rows={rows}/></>:<p>No stock with an expiry date runs out within {days} days.</p>)}
 </Panel>;
}

/** Change an ingredient's cost and levels, and the packs it is bought in. */
export function IngredientEditor({ingredient,onClose,onSaved}){
 const action=useAction(onSaved),[packs,setPacks]=useState(ingredient.packs||[]);
 async function save(e){e.preventDefault();const v=Object.fromEntries(new FormData(e.currentTarget));if(await action.run(()=>http.put('/api/stock/ingredients/'+ingredient.id,{cost_per_unit:Number(v.cost_per_unit),min_level:Number(v.min_level),reorder_quantity:Number(v.reorder_quantity)})))onClose()}
 async function addPack(e){e.preventDefault();const form=e.currentTarget,v=Object.fromEntries(new FormData(form));let saved;if(await action.run(async()=>{saved=await http.post('/api/stock/ingredients/'+ingredient.id+'/packs',{name:v.name.trim(),factor:Number(v.factor)})})){setPacks(saved.packs);form.reset()}}
 async function removePack(pack){let saved;if(await action.run(async()=>{saved=await http.delete('/api/stock/ingredients/'+ingredient.id+'/packs/'+pack.id)}))setPacks(saved.packs)}
 return <WorkspaceDialog title={'Edit '+ingredient.name} onClose={onClose}><ActionFeedback action={action}/>
  <form className="live-form" onSubmit={save}><Field label={'Cost per '+ingredient.unit+' (KES)'}><input name="cost_per_unit" type="number" min="0" step="0.0001" required defaultValue={ingredient.cost_per_unit}/></Field><Field label="Minimum level"><input name="min_level" type="number" min="0" step="0.000001" required defaultValue={ingredient.min_level}/></Field><Field label="Reorder quantity"><input name="reorder_quantity" type="number" min="0" step="0.000001" required defaultValue={ingredient.reorder_quantity}/></Field><p>A new cost applies from now on. Food already prepared keeps the cost it had then.</p><button className="btn primary" disabled={action.busy}>Save</button></form>
  <h3>Packs</h3><p>Deliveries and counts can be entered in packs, for example a 50 kg bag or a crate of 24. They are turned into {ingredient.unit} automatically.</p>
  {packs.length>0&&<ul className="pack-list">{packs.map(p=><li key={p.id}><span>1 {p.name} = {p.factor} {ingredient.unit}</span><button type="button" className="btn" disabled={action.busy} onClick={()=>removePack(p)}>Remove</button></li>)}</ul>}
  <form className="live-form" onSubmit={addPack}><Field label="Pack name"><input name="name" required maxLength={40} placeholder="e.g. 50 kg bag"/></Field><Field label={ingredient.unit+' in one pack'}><input name="factor" type="number" min="0.000001" step="0.000001" required/></Field><button className="btn" disabled={action.busy}>Add pack</button></form>
 </WorkspaceDialog>;
}

/** Pack, price and expiry fields for one stock document line. */
export function LineExtras({ingredient,line,kind,update,index}){
 const packs=ingredient?.packs||[],priced=['receiving','purchase'].includes(kind),dated=kind==='receiving';
 const unit=line.pack||ingredient?.unit||'unit';
 return <>{packs.length>0&&<Field label={'Entered in '+(index+1)}><select value={line.pack||''} onChange={e=>update({pack:e.target.value})}><option value="">{ingredient.unit}</option>{packs.map(p=><option key={p.id} value={p.name}>{p.name} ({p.factor} {ingredient.unit})</option>)}</select></Field>}
  {priced&&<Field label={'Price per '+unit+' (KES) '+(index+1)}><input type="number" min="0" step="0.01" value={line.unit_cost??''} placeholder="Optional" onChange={e=>update({unit_cost:e.target.value})}/></Field>}
  {dated&&<Field label={'Expiry date '+(index+1)}><input type="date" value={line.expiry_date||''} onChange={e=>update({expiry_date:e.target.value})}/></Field>}</>;
}

/** A document line as the API expects it. */
export const lineBody=l=>({ingredient_id:Number(l.ingredient_id),quantity:Number(l.quantity),...(l.pack?{pack:l.pack}:{}),...(l.unit_cost!==''&&l.unit_cost!=null?{unit_cost:Number(l.unit_cost)}:{}),...(l.expiry_date?{expiry_date:l.expiry_date}:{})});
