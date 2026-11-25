import {useState} from 'react';
import {http} from '../services/http';
import {useData,useAction,Feedback,EntryForm,Table,Panel} from '../pages/LiveUI';

/** The print program at each branch, which collects kitchen tickets from the cloud server. */
export default function PrintAgents(){
 const rows=useData('/api/print-agents'),branches=useData('/api/branches'),[made,setMade]=useState(null),action=useAction(rows.reload);
 const seen=v=>v?new Date(/[Z+]/.test(v)?v:v+'Z').toLocaleString():'Never';
 return <Panel title="Print program at each branch"><p>The system runs in the cloud, so it cannot reach printers on a branch's own network. Install the print program on a computer that stays on at the branch (see the print program guide). While a branch has a print program, its kitchen tickets wait until the program collects and prints them, usually within a few seconds.</p>
  <Feedback query={rows}/><Feedback query={branches}/>
  {made?<div className="cashier-warning" role="status"><p><strong>Key for {made.name} ({made.branch}).</strong> Copy it into the print program's settings now. It is shown only once.</p><code style={{wordBreak:'break-all'}}>{made.key}</code><p><button className="btn" onClick={()=>navigator.clipboard?.writeText(made.key)}>Copy key</button> <button className="btn" onClick={()=>setMade(null)}>Done</button></p></div>:
  <EntryForm action={action} fields={[{name:'branch_id',label:'Branch',options:(branches.data||[]).filter(b=>b.is_active!==false).map(b=>({value:b.id,label:b.name}))},{name:'name',label:'Computer name (e.g. Kitchen PC)'}]}
   onSave={v=>action.run(async()=>setMade(await http.post('/api/print-agents',{branch_id:Number(v.branch_id),name:v.name.trim()})))}/>}
  <Table columns={[['branch','Branch'],['name','Computer'],['is_active','State',(v,r)=>!v?'Removed':r.online?'Connected':'Not connected'],['last_seen','Last checked in',seen]]} rows={rows.data||[]}
   actions={r=>r.is_active&&<button className="btn" disabled={action.busy} onClick={()=>action.run(()=>http.delete('/api/print-agents/'+r.id))}>Remove</button>}/>
 </Panel>;
}
