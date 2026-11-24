import {useState} from 'react';
import WorkspaceDialog from '../components/WorkspaceDialog';
import {http} from '../services/http';
import {useAuth} from '../auth/AuthContext';
import {useData,useAction,Feedback,ActionFeedback,EntryForm,Table,PageHeader,Panel,Search,matching} from './LiveUI';

const list=data=>Array.isArray(data)?data:[];

/** Which branch the app is working in. Directors without a home branch can switch. */
export function useBranchContext(){
 const {user}=useAuth();
 const branches=useData('/api/branches');
 const selected=localStorage.getItem('b360_branch');
 const rows=list(branches.data);
 const canSwitch=user.role==='director'&&user.branch_id==null;
 const current=canSwitch?(selected?rows.find(b=>String(b.id)===selected):null):rows.find(b=>b.id===user.branch_id);
 return {branches:rows,current,canSwitch,label:current?.name||(canSwitch?'All branches':'')};
}

export function BranchPicker(){
 const {branches,current,canSwitch,label}=useBranchContext();
 if(!canSwitch)return <strong>{label||'Branch'}</strong>;
 function choose(value){
  if(value)localStorage.setItem('b360_branch',value);else localStorage.removeItem('b360_branch');
  window.location.reload(); // every screen reloads its data for the chosen branch
 }
 return <label className="branch-picker"><span className="sr-only">Working branch</span>
  <select aria-label="Working branch" value={current?String(current.id):''} onChange={e=>choose(e.target.value)}>
   <option value="">All branches</option>
   {branches.filter(b=>b.is_active||String(b.id)===String(current?.id)).map(b=><option key={b.id} value={b.id}>{b.name}</option>)}
  </select></label>;
}

const fields=[{name:'name',label:'Branch name'},{name:'code',label:'Short code (letters, numbers, dashes)'},{name:'address',label:'Address',required:false},{name:'phone',label:'Phone',required:false}];
const columns=[['name','Branch'],['code','Code'],['address','Address'],['phone','Phone'],['is_active','Status',v=>v?'Open':'Closed']];

export default function Branches(){
 const query=useData('/api/branches');const action=useAction(query.reload);
 const [search,setSearch]=useState(''),[draft,setDraft]=useState(null),[menuFor,setMenuFor]=useState(null);
 const rows=matching(list(query.data),search);
 async function save(e){e.preventDefault();await action.run(async()=>{
  await http.put('/api/branches/'+draft.id,{name:draft.name,address:draft.address||null,phone:draft.phone||null,is_active:draft.is_active});setDraft(null);
 })}
 return <><PageHeader title="Branches" subtitle="Each branch keeps its own tables, bills, cash, stock and car-wash bays. The menu is shared." action="Refresh" onAction={query.reload}/><Feedback query={query}/>
  <Panel title="Add branch"><EntryForm fields={fields} action={action} onSave={v=>action.run(()=>http.post('/api/branches',v))}/></Panel>
  <Panel title="All branches"><div className="live-actions"><Search value={search} onChange={setSearch}/></div>
   <Table columns={columns} rows={rows} actions={row=><><button className="btn" onClick={()=>setDraft({...row})}>Edit</button><button className="btn" onClick={()=>setMenuFor(row)}>Menu availability</button></>}/></Panel>
  {draft&&<WorkspaceDialog title={'Edit '+draft.name} onClose={()=>setDraft(null)}><form className="live-form" onSubmit={save}>
   <label className="field">Branch name<input value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} required/></label>
   <label className="field">Address<input value={draft.address||''} onChange={e=>setDraft({...draft,address:e.target.value})}/></label>
   <label className="field">Phone<input value={draft.phone||''} onChange={e=>setDraft({...draft,phone:e.target.value})}/></label>
   <label className="field checkbox"><input type="checkbox" checked={draft.is_active} onChange={e=>setDraft({...draft,is_active:e.target.checked})}/> Open (staff of a closed branch cannot sign in to work)</label>
   <ActionFeedback action={action}/><button className="btn primary" disabled={action.busy}>Save branch</button></form></WorkspaceDialog>}
  {menuFor&&<WorkspaceDialog title={'Menu at '+menuFor.name} onClose={()=>setMenuFor(null)}><BranchMenu branchId={menuFor.id}/></WorkspaceDialog>}
 </>;
}

/** Switch shared menu items on or off at one branch. */
export function BranchMenu({branchId}){
 const {user}=useAuth();const id=branchId??user.branch_id;
 const query=useData(id?`/api/branches/${id}/menu`:'/health');const action=useAction(query.reload);
 const [search,setSearch]=useState('');
 if(!id)return <p>Choose a branch to manage its menu.</p>;
 const rows=matching(list(query.data),search);
 return <><Feedback query={query}/><ActionFeedback action={action}/><div className="live-actions"><Search value={search} onChange={setSearch}/></div>
  <Table columns={[['name','Menu item'],['available','At this branch',v=>v?'Available':'Switched off']]} rows={rows.map(r=>({...r,id:r.menu_item_id}))}
   actions={row=><button className="btn" disabled={action.busy} onClick={()=>action.run(()=>http.put(`/api/branches/${id}/menu/${row.menu_item_id}`,{available:!row.available}))}>{row.available?'Switch off':'Switch on'}</button>}/></>;
}

export function BranchMenuPage(){
 return <><PageHeader title="Branch menu" subtitle="Switch shared menu items off when this branch cannot serve them. Prices are set in Menu."/><Panel title="Menu items"><BranchMenu/></Panel></>;
}
