import {useState} from 'react';
import WorkspaceDialog,{exportRows} from '../components/WorkspaceDialog';
import {Link} from 'react-router-dom';
import {http} from '../services/http';
import {resourceService as api} from '../services/resourceService';
import {useAuth} from '../auth/AuthContext';
import MenuConfiguration from './MenuConfiguration';
import {useData,useAction,Feedback,EntryForm,Table,number,options,money,PageHeader,Panel,Field,Search,matching,ActionFeedback} from './LiveUI';

export function Configuration({resource,title}){
 return resource==='menu'?<MenuConfiguration/>:<GenericConfiguration resource={resource} title={title}/>;
}
function GenericConfiguration({resource,title}){
 const query=useData(resource==='printers'?'/api/admin/departments':({menu:'/api/admin/menu',users:'/api/admin/users',departments:'/api/admin/departments',categories:'/api/admin/categories',bays:'/api/carwash/bays',services:'/api/carwash/services',audits:'/api/admin/audit-logs'}[resource]));
 const action=useAction(query.reload),{user}=useAuth(),categories=useData(resource==='menu'?'/api/admin/categories':'/health'),departments=useData(['menu','users'].includes(resource)?'/api/admin/departments':'/health');
 const branches=useData(resource==='users'&&user.role==='director'?'/api/branches':'/health');
 const branchName=id=>id==null?'All branches':((Array.isArray(branches.data)?branches.data:[]).find(b=>b.id===id)?.name||id);
 const configs={
 menu:{fields:[{name:'name',label:'Item name'},number('price','Price'),{name:'category_id',label:'Category',options:options(categories.data)},{name:'department_id',label:'Department',options:options(departments.data)}],columns:[['name','Name'],['price','Price',money],['category','Category'],['department','Department']]},
 users:{fields:[{name:'username',label:'Email',type:'email'},{name:'full_name',label:'Full name'},{name:'password',label:'Temporary password',type:'password'},{name:'role',label:'Role',options:user.role==='director'?['director','manager','cashier','waiter','store_manager','carwash_manager','kitchen']:['cashier','waiter','store_manager','carwash_manager','kitchen']},{name:'department_id',label:'Kitchen department (required for kitchen accounts)',required:false,options:options(departments.data)},...(user.role==='director'?[{name:'branch_id',label:'Branch (leave empty for a director of all branches)',required:false,options:options((Array.isArray(branches.data)?branches.data:[]).filter(b=>b.is_active))}]:[])],columns:[['username','Email'],['full_name','Name'],['role','Role'],...(user.role==='director'?[['branch_id','Branch',branchName]]:[]),['active','Active']]},
 categories:{fields:[{name:'name',label:'Category name'},{name:'description',label:'Description',required:false}],columns:[['name','Name'],['description','Description']]},
 departments:{fields:[{name:'name',label:'Department name'},{name:'printer_ip',label:'Printer LAN IP',required:false},number('printer_port','Printer port',9100)],columns:[['name','Name'],['printer_ip','Printer IP'],['printer_port','Port']]},
 printers:{fields:[{name:'department_id',label:'Department',options:options(query.data)},{name:'printer_ip',label:'Printer LAN IP'},number('printer_port','Printer port',9100)],columns:[['name','Department'],['printer_ip','Printer IP'],['printer_port','Port']]},
 bays:{fields:[number('bay_number','Bay number',1),{name:'name',label:'Bay name'}],columns:[['bay_number','Number'],['name','Bay'],['is_active','Active']]},
 services:{fields:[{name:'name',label:'Service name'},number('price','Price'),number('duration_minutes','Duration in minutes',30)],columns:[['name','Service'],['price','Price',money],['duration_minutes','Minutes']]},
 audits:{fields:[],columns:[['timestamp','Time'],['user_id','User'],['action','Action'],['module','Module'],['entity_id','Record']]}
 };
 const config=configs[resource];
 const [search,setSearch]=useState(''),[selected,setSelected]=useState(null),[draft,setDraft]=useState(null);
 const canEdit=resource!=='audits',previewEdit=['bays','services'].includes(resource);
 const [previewEdits,setPreviewEdits]=useState([]);
 const rows=matching(query.data||[],search);
 const editFields=resource==='users'?configs.users.fields.filter(f=>!['username','password'].includes(f.name)):resource==='printers'?configs.printers.fields.filter(f=>f.name!=='department_id'):config.fields;
 async function saveEdit(e){e.preventDefault();if(previewEdit){setPreviewEdits(old=>[...old.filter(x=>x.id!==draft.id),{...draft}]);setDraft(null);return}await action.run(async()=>{
 const values=Object.fromEntries(editFields.map(f=>[f.name,f.type==='number'?Number(draft[f.name]):draft[f.name]]));
 if(resource==='users'){values.active=draft.active;values.department_id=values.department_id?Number(values.department_id):null;if('branch_id' in values)values.branch_id=values.branch_id?Number(values.branch_id):null}
 if(resource==='bays')values.is_active=draft.is_active;
 if(resource==='printers')await http.post('/api/admin/printer-config',{...values,department_id:draft.id});else await api.update(resource,draft.id,values);
 setDraft(null);
 })}

 return <><PageHeader title={title} subtitle="Configuration saved to the database" action="Refresh" onAction={query.reload}/><Feedback query={query}/>
 {resource==='menu'&&<><Feedback query={categories}/><Feedback query={departments}/><Link className="btn" to={'/'+user.role+'/categories'}>Manage categories</Link><Link className="btn" to={'/'+user.role+'/departments'}>Manage departments</Link></>}
 {config.fields.length>0&&<Panel title={resource==='printers'?'Configure printer':'Add record'}><EntryForm fields={config.fields} action={action} onSave={v=>action.run(()=>resource==='printers'?http.post('/api/admin/printer-config',v):api.create(resource,resource==='users'?{...v,department_id:v.department_id?Number(v.department_id):null,branch_id:v.branch_id?Number(v.branch_id):null}:v))}/></Panel>}
 <Panel title={title}><div className="live-actions"><Search value={search} onChange={setSearch}/><button className="btn" disabled={!rows.length} onClick={()=>exportRows(resource,config.columns,rows)}>Export current view</button></div><Table columns={config.columns} rows={rows} actions={row=><><button className="btn" onClick={()=>setSelected(row)}>Details</button>{canEdit&&<button className="btn" onClick={()=>setDraft({...row})}>Edit</button>}</>}/></Panel>
 {previewEdits.length>0&&<Panel title="Preview edits — not applied to live records"><p>These changes are available for frontend review only and reset when you leave.</p><Table columns={config.columns} rows={previewEdits}/><button className="btn" onClick={()=>setPreviewEdits([])}>Discard preview edits</button></Panel>}
 {selected&&<WorkspaceDialog title={selected.full_name||selected.name||'Record details'} onClose={()=>setSelected(null)}><dl className="record-detail">{config.columns.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{String(selected[key]??'?')}</dd></div>)}</dl>{resource==='audits'&&<><h3>Before</h3><pre className="audit-values">{JSON.stringify(selected.old_values||{},null,2)}</pre><h3>After</h3><pre className="audit-values">{JSON.stringify(selected.new_values||{},null,2)}</pre></>}</WorkspaceDialog>}
 {draft&&<WorkspaceDialog title={'Edit '+(draft.full_name||draft.name||'record')} onClose={()=>setDraft(null)}><form onSubmit={saveEdit} className="live-form">{previewEdit&&<div className="preview-notice"><strong>Frontend preview</strong>This edit will not update the live record.</div>}<fieldset disabled={action.busy}>{editFields.map(f=><Field key={f.name} label={f.label}>{f.options?<select required={f.required!==false} value={draft[f.name]??''} onChange={e=>setDraft({...draft,[f.name]:e.target.value})}>{f.options.map(o=><option key={o.value??o} value={o.value??o}>{o.label??o}</option>)}</select>:<input required={f.required!==false} type={f.type||'text'} min={f.min} step={f.type==='number'?'any':undefined} value={draft[f.name]??''} onChange={e=>setDraft({...draft,[f.name]:e.target.value})}/>}</Field>)}{['users','bays'].includes(resource)&&<Field label="Active"><select value={String(draft[resource==='users'?'active':'is_active'])} onChange={e=>setDraft({...draft,[resource==='users'?'active':'is_active']:e.target.value==='true'})}><option value="true">Active</option><option value="false">Inactive</option></select></Field>}<button className="btn primary">{previewEdit?'Save preview':'Save changes'}</button></fieldset><ActionFeedback action={action}/></form></WorkspaceDialog>}
 </>;
}
