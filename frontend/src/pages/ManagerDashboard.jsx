import {Link} from 'react-router-dom';
import {CalendarDays,Receipt,Clock3,Users,Printer,UtensilsCrossed,TriangleAlert,ArrowRight,RefreshCw} from 'lucide-react';
import {useLive,LiveState} from './WaiterWorkspace';
import {money} from './LiveUI';

const stages=[['pending','New'],['printed','In Kitchen'],['ready','Ready'],['payment_pending','Awaiting Payment']];
const parseDate=value=>new Date(value&&(/[Z+]\d*:?\d*$/.test(value)?value:value+'Z'));
const time=value=>parseDate(value).toLocaleTimeString('en-KE',{timeZone:'Africa/Nairobi',hour:'2-digit',minute:'2-digit'});
function Section({title,icon:Icon,action,children,className=''}){return <section className={'operations-panel '+className}><div className="operations-panel-head"><h2><Icon/>{title}</h2>{action}</div>{children}</section>}
function Go({to,children}){return <Link className="operations-link" to={'/manager/'+to}>{children}<ArrowRight size={16}/></Link>}

export default function ManagerDashboard(){
 const orders=useLive('/api/orders?active=true&sort=oldest&limit=100&offset=0'),menu=useLive('/api/admin/menu'),staff=useLive('/api/admin/users'),departments=useLive('/api/admin/departments');
 const queries=[orders,menu,staff,departments],rows=orders.data||[],people=staff.data||[],printers=departments.data||[];
 const loaded=orders.data!==null&&!orders.error;
 const deliveries=rows.flatMap(o=>(o.batches||[]).flatMap(b=>b.deliveries||[]));
 const queue=deliveries.filter(d=>d.status==='queued').length;
 const uncertain=deliveries.filter(d=>['uncertain','failed'].includes(d.status)).length;
 const slow=rows.filter(o=>['pending','printed'].includes(o.status)&&(Date.now()-parseDate(o.created_at))/60000>15);
 const date=new Date().toLocaleDateString('en-KE',{timeZone:'Africa/Nairobi',weekday:'short',day:'numeric',month:'short',year:'numeric'});
 const metrics=[{label:'Open Orders',value:loaded?rows.length+(rows.length===100?'+':''):'—',note:rows.length===100?'Oldest 100 bills shown':'Across restaurant tables',icon:Receipt},{label:'Avg Prep Time',value:'—',note:'Prep timing not recorded',icon:Clock3},{label:'Active Staff',value:staff.data&&!staff.error?people.filter(p=>p.active).length:'—',note:'Enabled staff accounts',icon:Users},{label:'Printer Queue',value:loaded?queue:'—',note:loaded?uncertain+' deliveries need checking':'Waiting for order data',icon:Printer}];
 return <div className="operations-dashboard">
  <div className="operations-heading"><div><h1>Operations Manager</h1><p><i/>Main Branch · Live operations</p></div><div className="operations-heading-actions"><span><CalendarDays/>{date}</span><button className="btn" onClick={()=>queries.forEach(q=>q.reload())}><RefreshCw/>Refresh</button><span className="operations-branch">Main Branch</span></div></div>
  <div className="operations-shortcuts"><Link to="/manager/tables">Tables</Link><Link to="/manager/bill-changes">Bill approvals</Link><Link to="/manager/departments">Departments</Link></div>
  <div className="operations-metrics">{metrics.map(({label,value,note,icon:Icon})=><article key={label}><div className="operations-metric-icon"><Icon/></div><div><span>{label}</span><strong>{value}</strong><small>{note}</small></div></article>)}</div>
  <div className="operations-main">
   <Section title="Order Pipeline" icon={UtensilsCrossed} action={<Go to="order-pipeline">View All Orders</Go>}>
    <LiveState query={orders}/><p className="operations-caption">Live restaurant bills · oldest first</p>
    <div className="operations-pipeline pipeline-rows">{stages.map(([status,label])=><div className={'operations-stage stage-'+status} key={status}><h3>{label} <span>({rows.filter(o=>o.status===status).length})</span></h3><div className="operations-tickets">{rows.filter(o=>o.status===status).map(o=><Link className="operations-ticket" key={o.id} to="/manager/order-pipeline"><div><strong>{o.order_number}</strong><time>{time(o.created_at)}</time></div><span>{o.table_number?'Table '+o.table_number:'Unassigned table'}</span><span>{o.waiter}</span><ul>{o.items.filter(i=>i.quantity>0).map((i,n)=><li key={i.id??n}>{i.quantity} × {i.name}</li>)}</ul><div><b>{money(o.total)}</b><em>{label}</em></div></Link>)}{loaded&&!rows.some(o=>o.status===status)&&<p className="operations-empty">No bills at this stage</p>}</div></div>)}</div>
   </Section>
   <div className="operations-side">
    <Section title="Kitchen Attention" icon={TriangleAlert} className={slow.length?'operations-alert warning':'operations-alert'}><p>{!loaded?'Waiting for order data.':slow.length?<><strong>{slow.length} bills</strong> opened over 15 minutes ago are still new or in the kitchen.</>:'No new or in-kitchen bills older than 15 minutes.'}</p><small>Based on bill opening time, not measured preparation time.</small><Go to="order-pipeline">View Orders</Go></Section>
    <Section title="Menu Availability" icon={UtensilsCrossed} action={<Go to="menu">Manage Menu</Go>}><LiveState query={menu}/><div className="operations-availability">{(menu.data||[]).slice(0,8).map(m=><div key={m.id}><i className={m.active?'available':'unavailable'}/><span>{m.name}</span><small className={m.active?'available':'unavailable'}>{m.active?'Available':'Unavailable'}</small></div>)}{menu.data?.length===0&&<p className="operations-empty">Add food items in Manage Menu.</p>}</div></Section>
   </div>
  </div>
  <div className="operations-bottom">
   <Section title="Staff Activity" icon={Users} action={<Go to="staff">View All Staff</Go>}><LiveState query={staff}/><p className="operations-caption">Open bills in the pipeline · shift attendance and ratings are not tracked</p><div className="table-scroll"><table><thead><tr><th>#</th><th>Name</th><th>Role</th><th>Open bills</th><th>Account</th></tr></thead><tbody>{people.filter(p=>p.role==='waiter').map((p,n)=><tr key={p.id}><td>{n+1}</td><td>{p.full_name||p.username}</td><td>Waiter</td><td>{loaded?rows.filter(o=>o.waiter_id===p.id).length:'—'}</td><td>{p.active?'Active':'Inactive'}</td></tr>)}</tbody></table>{staff.data&&!people.some(p=>p.role==='waiter')&&<p className="operations-empty">No waiter accounts configured.</p>}</div></Section>
   <Section title="Printer Status" icon={Printer} action={<Go to="printers">Manage Printers</Go>}><LiveState query={departments}/><p className="operations-caption">Delivery records · device connectivity is not monitored</p><div className="table-scroll"><table><thead><tr><th>Printer</th><th>Configuration</th><th>Queue</th><th>Check delivery</th></tr></thead><tbody>{printers.map(p=><tr key={p.id}><td>{p.name}</td><td><span className={'operations-dot '+(p.printer_ip?'available':'unavailable')}/>{p.printer_ip?'Configured':'Not configured'}</td><td>{loaded?deliveries.filter(d=>d.department_id===p.id&&d.status==='queued').length:'—'}</td><td>{loaded?deliveries.filter(d=>d.department_id===p.id&&['uncertain','failed'].includes(d.status)).length:'—'}</td></tr>)}</tbody></table>{departments.data?.length===0&&<p className="operations-empty">Configure departments and printers to get started.</p>}</div></Section>
  </div>
 </div>;
}
