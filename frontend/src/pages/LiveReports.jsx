import {useState} from 'react';
import {Link} from 'react-router-dom';
import {request} from '../services/http';
import RevenueBars from '../components/RevenueBars';
import {useData,useAction,Feedback,ActionFeedback,Table,Field,money,PageHeader,Panel,StatGrid} from './LiveUI';
export function Overview(){
 const query=useData('/api/dashboard'),[period,setPeriod]=useState('weekly'),trends=useData('/api/dashboard/trends?period='+period),data=query.data;
 return <><PageHeader title="Good morning, Director" subtitle="Confirmed receipts and current stock" action="Refresh" onAction={()=>{query.reload();trends.reload()}}/><Feedback query={query}/>{data&&<>
 <StatGrid items={[{label:'Restaurant revenue',value:money(data.revenue.restaurant.total)},{label:'Car wash revenue',value:money(data.revenue.carwash.total)},{label:'Combined revenue',value:money(data.revenue.combined)},{label:'Low stock items',value:data.stock_alerts.count}]}/>
 <Panel title="Revenue trends"><Field label="Period"><select value={period} onChange={e=>setPeriod(e.target.value)}><option value="daily">Today</option><option value="weekly">Last 7 days</option><option value="monthly">Last 30 days</option></select></Field><Feedback query={trends}/>{trends.data&&<><RevenueBars points={trends.data.points}/><Table columns={[['date','Date'],['restaurant','Restaurant',money],['carwash','Car wash',money],['total','Total',money]]} rows={trends.data.points}/></>}</Panel>
 <div className="two-columns"><Panel title="Top selling items"><p>Item sales are before payment-level refunds.</p><Table columns={[['item','Item'],['quantity','Quantity'],['revenue','Revenue',money]]} rows={data.top_items}/></Panel><Panel title="Low stock"><Table columns={[['ingredient','Ingredient'],['current','Current'],['min','Minimum'],['unit','Unit']]} rows={data.stock_alerts.items}/></Panel></div></>}
 <Panel title="Administration"><div className="live-actions">{[['menu','Menu'],['management','Staff accounts'],['departments','Departments'],['printers','Printers'],['bay-config','Wash bays'],['service-types','Wash services'],['audit','Audit history'],['branches','Branches'],['settings','Settings'],['notifications','Notifications']].map(([id,label])=><Link className="btn" key={id} to={'/director/'+id}>{label}</Link>)}</div></Panel></>;
}
export function Reports(){
 const initial=new Date(),localDate=[initial.getFullYear(),String(initial.getMonth()+1).padStart(2,'0'),String(initial.getDate()).padStart(2,'0')].join('-');
 const [period,setPeriod]=useState('daily'),[day,setDay]=useState(localDate),parts=day.split('-');
 const query=useData('/api/reports/'+period+(period==='daily'?'?date='+day:period==='weekly'?'?week_start='+day:'?year='+parts[0]+'&month='+Number(parts[1]))),action=useAction();
 async function download(format){await action.run(async()=>{const blob=await request('/api/reports/export?format='+format+'&from_date='+query.data.start+'&to_date='+query.data.end,{responseType:'blob'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='biashara360-'+day+'.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}
 return <><PageHeader title="Reports" subtitle="Net receipts after refunds; stock alerts show current levels" action="Refresh" onAction={query.reload}/><div className="live-actions"><Field label="Report period"><select value={period} onChange={e=>setPeriod(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></Field><Field label="Report date / week start"><input type="date" required value={day} onChange={e=>{if(e.target.value)setDay(e.target.value)}}/></Field></div><Feedback query={query}/><ActionFeedback action={action}/>
 {query.data&&<><p>Restaurant receipts before refunds: {money(query.data.totals.restaurant_gross ?? query.data.totals.restaurant)} ? Refunds recorded in this period: {money(query.data.totals.restaurant_refunds||0)}</p><StatGrid items={[{label:'Restaurant',value:money(query.data.totals.restaurant)},{label:'Car wash',value:money(query.data.totals.carwash)},{label:'Combined',value:money(query.data.totals.combined)}]}/><div className="live-actions"><button className="btn" disabled={action.busy} onClick={()=>download('csv')}>Download CSV</button><button className="btn" disabled={action.busy} onClick={()=>download('pdf')}>Download PDF</button></div>
 <Panel title="Daily breakdown"><RevenueBars points={query.data.days}/><Table columns={[['date','Date'],['restaurant','Restaurant',money],['carwash','Car wash',money],['total','Total',money],['orders_count','Orders'],['washes_count','Washes']]} rows={query.data.days}/></Panel>
 <Panel title="Top selling items"><p>Item sales are before payment-level refunds.</p><Table columns={[['item','Item'],['quantity','Quantity'],['revenue','Revenue',money]]} rows={query.data.top_items||query.data.restaurant?.top_items||[]}/></Panel><Panel title="Current low stock"><Table columns={[['ingredient','Ingredient'],['current','Current'],['min','Minimum'],['unit','Unit']]} rows={query.data.stock.low_items}/></Panel><ProfitVat from={query.data.start} to={query.data.end}/></>}</>;
}

/** Restaurant profit (sales without VAT minus food cost) and VAT by rate for the chosen period. */
export function ProfitVat({from,to}){
 const query=useData('/api/reports/profit-vat?from_date='+from+'&to_date='+to),data=query.data,r=data?.restaurant;
 return <Panel title="Profit and VAT"><Feedback query={query}/>{data&&<>
  <p>Restaurant prices include VAT. Food cost is the ingredients taken out of stock to prepare the dishes sold, at their cost on that day.</p>
  <StatGrid items={[{label:'Sales without VAT (after refunds)',value:money(r.net_sales)},{label:'Food cost',value:money(r.food_cost)},{label:'Gross profit',value:money(r.gross_profit)+(r.gross_margin_percent!=null?' ('+r.gross_margin_percent+'%)':'')},{label:'VAT due',value:money(data.vat.vat_due)}]}/>
  <Table columns={[['label','Line'],['value','Amount (KES)',money]]} rows={[
   {label:'Sales including VAT',value:r.sales_gross},{label:'VAT on sales',value:r.sales_vat},
   {label:'Refunds (credit notes) including VAT',value:r.refunds_gross},{label:'VAT on credit notes',value:r.refunds_vat},
   {label:'Sales without VAT, after refunds',value:r.net_sales},{label:'Food cost',value:r.food_cost},{label:'Gross profit',value:r.gross_profit},
   {label:'Stock written off (wastage and count differences)',value:r.stock_written_off},{label:'Profit after write-offs',value:r.profit_after_write_offs}]}/>
  <h3>VAT by rate</h3><Table columns={[['rate','Rate',v=>v+'%'],['gross','Sales incl. VAT',money],['vat','VAT',money],['net','Sales excl. VAT',money]]} rows={data.vat.rates}/>
  {data.vat.sales_without_rate>0&&<p>{money(data.vat.sales_without_rate)} of sales are from bills made before VAT rates were recorded, so no VAT is worked out for them.</p>}
  <p>Car wash takings: {money(data.carwash.revenue)}. {data.carwash.note}</p>
  <h3>Profit by dish</h3><Table columns={[['item','Dish'],['quantity','Sold'],['net','Sales excl. VAT',money],['food_cost','Food cost',money],['gross_profit','Gross profit',money]]} rows={data.items}/>
  {data.notes.units_without_cost>0&&<p>{data.notes.units_without_cost} dish(es) sold have no food cost because they have no recipe or were never sent to preparation. Their profit is overstated.</p>}
  {data.notes.estimated_cost_lines>0&&<p>{data.notes.estimated_cost_lines} dish line(s) were prepared before costs were recorded on stock movements, so today's ingredient cost is used for them.</p>}
 </>}</Panel>;
}
