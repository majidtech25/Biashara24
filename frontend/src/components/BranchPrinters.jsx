import {http} from '../services/http';
import {useData,useAction,Feedback,EntryForm,Table,Panel} from '../pages/LiveUI';

/** Each branch's printer for a department. A department with none here uses its own printer. */
export default function BranchPrinters(){
 const rows=useData('/api/admin/branch-printers'),branches=useData('/api/branches'),departments=useData('/api/admin/departments'),action=useAction(rows.reload);
 const branchList=(branches.data||[]).filter(b=>b.is_active!==false);
 if(branches.data&&branchList.length<2&&!(rows.data||[]).length)return null;
 return <Panel title="Printers per branch"><p>Each branch can send a department's tickets to its own printer. A department with no printer set here prints to the department printer above. Tickets the printer could not receive are tried again automatically for 30 minutes; a ticket that may already have printed is never sent twice without a manager.</p>
  <Feedback query={rows}/><Feedback query={branches}/><Feedback query={departments}/>
  <EntryForm action={action} fields={[
   {name:'branch_id',label:'Branch',options:branchList.map(b=>({value:b.id,label:b.name}))},
   {name:'department_id',label:'Department',options:(departments.data||[]).map(d=>({value:d.id,label:d.name}))},
   {name:'printer_ip',label:'Printer IP address (e.g. 192.168.1.50)'},
   {name:'printer_port',label:'Port',type:'number',value:'9100'}
  ]} onSave={v=>action.run(()=>http.put('/api/admin/branch-printers',{branch_id:Number(v.branch_id),department_id:Number(v.department_id),printer_ip:v.printer_ip.trim(),printer_port:Number(v.printer_port||9100)}))}/>
  <Table columns={[['branch','Branch'],['department','Department'],['printer_ip','Printer'],['printer_port','Port']]} rows={rows.data||[]} actions={r=><button className="btn" disabled={action.busy} onClick={()=>action.run(()=>http.delete('/api/admin/branch-printers/'+r.id))}>Remove</button>}/>
 </Panel>;
}
