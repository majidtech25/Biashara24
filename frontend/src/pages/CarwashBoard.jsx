import {useState} from 'react';
import WorkspaceDialog from '../components/WorkspaceDialog';
import {http} from '../services/http';
import {useData,useAction,Feedback,ActionFeedback,EntryForm,Table,PageHeader,Panel,money} from './LiveUI';

const list=data=>Array.isArray(data)?data:[];
const minutesSince=value=>value?Math.max(0,Math.round((Date.now()-new Date(value+(String(value).endsWith('Z')?'':'Z')).getTime())/60000)):null;
const STATUS={free:'Free',waiting:'Car waiting',washing:'Washing'};

/** Live bay board: which car is on which bay, who is washing it, and moving it along. */
export function BayBoard(){
 const board=useData('/api/carwash/board',15000),attendants=useData('/api/carwash/attendants');
 const action=useAction(board.reload);
 const [starting,setStarting]=useState(null),[attendant,setAttendant]=useState('');
 const active=list(attendants.data).filter(a=>a.is_active);
 const bays=list(board.data);
 const counts={free:bays.filter(b=>b.status==='free').length,waiting:bays.filter(b=>b.status==='waiting').length,washing:bays.filter(b=>b.status==='washing').length};
 async function start(e){e.preventDefault();if(await action.run(()=>http.put(`/api/carwash/${starting.wash.id}/wash`,{status:'washing',attendant_id:Number(attendant)}))){setStarting(null);setAttendant('')}}
 return <><PageHeader title="Bay board" subtitle={`${counts.free} free · ${counts.waiting} waiting · ${counts.washing} washing. Refreshes every 15 seconds.`} action="Refresh" onAction={board.reload}/>
  <Feedback query={board}/><ActionFeedback action={action}/>
  {!board.loading&&!bays.length&&<p>No open bays. Add bays in Bay Configuration.</p>}
  <div className="bay-board">{bays.map(bay=><article key={bay.id} className={'bay-card bay-'+bay.status} aria-label={`Bay ${bay.bay_number}`}>
   <div className="bay-card-title"><strong>Bay {bay.bay_number}</strong><span>{bay.name}</span></div>
   <p className="bay-status">{STATUS[bay.status]||bay.status}</p>
   {bay.wash?<><dl>
     <div><dt>Vehicle</dt><dd>{bay.wash.vehicle_plate}{bay.wash.vehicle_type?' · '+bay.wash.vehicle_type:''}</dd></div>
     <div><dt>Service</dt><dd>{bay.wash.service_name||'—'} · {money(bay.wash.amount)}</dd></div>
     <div><dt>Payment</dt><dd>{bay.wash.payment_status==='completed'?'Paid':'Awaiting confirmation'}</dd></div>
     {bay.wash.attendant&&<div><dt>Attendant</dt><dd>{bay.wash.attendant}</dd></div>}
     <div><dt>{bay.status==='washing'?'Washing for':'Waiting for'}</dt><dd>{minutesSince(bay.status==='washing'?bay.wash.wash_started_at:bay.wash.created_at)} min</dd></div>
    </dl>
    {bay.status==='waiting'&&<button className="btn primary" disabled={action.busy} onClick={()=>{setStarting(bay);setAttendant(bay.wash.attendant_id?String(bay.wash.attendant_id):'')}}>Start wash</button>}
    {bay.status==='washing'&&<button className="btn primary" disabled={action.busy} onClick={()=>action.run(()=>http.put(`/api/carwash/${bay.wash.id}/wash`,{status:'done'}))}>Finish wash</button>}
   </>:<p className="muted">Ready for the next car.</p>}
  </article>)}</div>
  {starting&&<WorkspaceDialog title={`Start wash on bay ${starting.bay_number}`} onClose={()=>setStarting(null)}><form className="live-form" onSubmit={start}>
   <p>{starting.wash.vehicle_plate} · {starting.wash.service_name}</p>
   <label className="field">Attendant<select required value={attendant} onChange={e=>setAttendant(e.target.value)}><option value="">Select…</option>{active.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
   {!active.length&&<p>No active attendants. Add them in Staff &amp; Attendants.</p>}
   <ActionFeedback action={action}/><button className="btn primary" disabled={action.busy||!attendant}>Start wash</button></form></WorkspaceDialog>}
 </>;
}

/** People who wash cars at this branch. They do not sign in. */
export function Attendants(){
 const query=useData('/api/carwash/attendants');const action=useAction(query.reload);
 const [draft,setDraft]=useState(null);
 async function save(e){e.preventDefault();if(await action.run(()=>http.put('/api/carwash/attendants/'+draft.id,{name:draft.name,phone:draft.phone||null,is_active:draft.is_active})))setDraft(null)}
 return <><PageHeader title="Staff & Attendants" subtitle="Car-wash attendants at this branch. Assign them when a wash starts." action="Refresh" onAction={query.reload}/><Feedback query={query}/>
  <Panel title="Add attendant"><EntryForm fields={[{name:'name',label:'Full name'},{name:'phone',label:'Phone',required:false}]} action={action} onSave={v=>action.run(()=>http.post('/api/carwash/attendants',{name:v.name,phone:v.phone||null}))}/></Panel>
  <Panel title="Attendants"><Table columns={[['name','Name'],['phone','Phone'],['is_active','Status',v=>v?'Active':'Inactive']]} rows={list(query.data)} actions={row=><button className="btn" onClick={()=>setDraft({...row})}>Edit</button>}/></Panel>
  {draft&&<WorkspaceDialog title={'Edit '+draft.name} onClose={()=>setDraft(null)}><form className="live-form" onSubmit={save}>
   <label className="field">Full name<input required value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
   <label className="field">Phone<input value={draft.phone||''} onChange={e=>setDraft({...draft,phone:e.target.value})}/></label>
   <label className="field">Status<select value={String(draft.is_active)} onChange={e=>setDraft({...draft,is_active:e.target.value==='true'})}><option value="true">Active</option><option value="false">Inactive</option></select></label>
   <ActionFeedback action={action}/><button className="btn primary" disabled={action.busy}>Save attendant</button></form></WorkspaceDialog>}
 </>;
}
