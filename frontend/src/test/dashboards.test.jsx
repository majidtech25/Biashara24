import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import App from '../App';
const account=vi.hoisted(()=>({role:'director'}));
vi.mock('../auth/AuthContext',()=>({AuthProvider:({children})=>children,useAuth:()=>({user:{id:1,role:account.role,username:'test',full_name:'Test User'},status:'authenticated',logout:vi.fn()})}));
const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
let ingredients,orders,payments,fetchMock;
const dashboard={revenue:{restaurant:{total:1234},carwash:{total:500},combined:1734},stock_alerts:{count:0,items:[]},top_items:[]};
beforeEach(()=>{
 localStorage.clear();
 ingredients=[{id:1,name:'Flour',current_stock:10,min_level:5,unit:'kg',is_low:false},{id:2,name:'Tomatoes',current_stock:2,min_level:5,unit:'kg',is_low:true}];
 orders=[{id:1,order_number:'B-LIVE-1',table_number:1,version:1,created_at:'2026-09-24T09:00:00',batches:[],change_requests:[],customer:'Table 1',waiter:'Waiter',total:320,status:'pending',items:[{id:1,name:'Tea',quantity:2,subtotal:320}]}];payments=[];
 fetchMock=vi.fn(async(url,init)=>{
 const path=new URL(url).pathname;
 if(path==='/health')return response({status:'ok'});
 if(path==='/api/dashboard')return response(dashboard);
 if(path==='/api/dashboard/trends')return response({points:[]});
 if(path==='/api/tables')return response([{id:1,number:1,is_active:true,occupied:false}]);
 if(path==='/api/cashier/shifts')return response([]);
 if(path==='/api/orders/1')return response(orders[0]);
 if(path==='/api/orders/2')return response(orders.find(o=>o.id===2));
 if(path==='/api/menu')return response([{id:1,name:'Tea',price:160}]);
 if(path==='/api/orders'&&init.method==='POST'){const body=JSON.parse(init.body);const o={...orders[0],id:2,order_number:'B-LIVE-2',items:body.items.map(i=>({...i,name:'Tea'}))};orders.push(o);return response(o,201)}
 if(path==='/api/orders')return response([...orders]);
 if(path==='/api/orders/1/clear'){const body=JSON.parse(init.body);const payment={id:5,order_id:1,order_number:'B-LIVE-1',amount:320,method:body.method,reference:body.reference,status:body.method==='cash'?'completed':'pending'};payments.push(payment);orders[0].status=body.method==='cash'?'cleared':'payment_pending';return response(payment,201)}
 if(path==='/api/payments/5/verify'){payments[0].status='completed';return response(payments[0])}
 if(path==='/api/payments/daily-summary')return response({cash_total:0,mpesa_total:0,total_revenue:0,orders_cleared:0});
 if(path==='/api/payments')return response([...payments]);
 if(path==='/api/stock/ingredients'&&init.method==='POST'){const item={...JSON.parse(init.body),id:3,is_low:false};ingredients.push(item);return response(item,201)}
 if(path==='/api/stock/ingredients')return response([...ingredients]);
 if(path==='/api/stock/history')return response([]);
 if(path==='/api/carwash/today')return response({transactions:[],summary:{total_washes:0,cash_total:0,mpesa_total:0,total_revenue:0}});
 if(path==='/api/carwash/history')return response({transactions:[],total:0});
 if(path.startsWith('/api/carwash/'))return response([]);
 if(path.startsWith('/api/admin/'))return response([]);
 return response({detail:'Not found'},404);
 });vi.stubGlobal('fetch',fetchMock);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
function open(path){account.role=path.split('/')[1];return render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>)}
describe('live workspaces',()=>{
 it('shows the manager operations dashboard with live bills and the reference navigation',async()=>{
  open('/manager/manager-dashboard');
  await screen.findByText('B-LIVE-1');
  expect(screen.getByRole('heading',{name:'Order Pipeline'})).toBeInTheDocument();
  expect(screen.getByRole('heading',{name:'Printer Status'})).toBeInTheDocument();
  expect(screen.getByText('Prep timing not recorded')).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Create order'})).not.toBeInTheDocument();
  expect(within(screen.getByRole('navigation',{name:'Main navigation'})).getAllByRole('link').map(a=>a.textContent)).toEqual(['Manager Dashboard','Orders','Menu','Staff','Printers','Reports']);
  expect(screen.getByRole('link',{name:'Manage Menu'})).toHaveAttribute('href','/manager/menu');
  expect(screen.getByRole('link',{name:'Manage Printers'})).toHaveAttribute('href','/manager/printers');
 });
 it('shows a manager connection error instead of inventing operational figures',async()=>{
  const original=fetchMock.getMockImplementation();
  fetchMock.mockImplementation((url,opts)=>new URL(url).pathname==='/api/orders'?Promise.resolve(response({detail:'Orders unavailable'},500)):original(url,opts));
  open('/manager/manager-dashboard');
  expect(await screen.findByRole('alert')).toHaveTextContent('Orders unavailable');
  expect(screen.queryByText('B-LIVE-1')).not.toBeInTheDocument();
  expect(screen.getByText('Waiting for order data.')).toBeInTheDocument();
 });
 it.each([['/director/overview','Good morning, Director'],['/manager/manager-dashboard','Operations Manager'],['/carwash_manager/wash-overview','Car Wash Manager'],['/store_manager/store-overview','Store & Inventory'],['/cashier/checkout','Cashier Station'],['/waiter/orders','My open bills']])('opens %s',(path,title)=>{open(path);expect(screen.getByRole('heading',{name:title,level:1})).toBeInTheDocument()});
 it('displays server revenue and only six director navigation links',async()=>{open('/director/overview');expect(await screen.findByText('KES 1,734')).toBeInTheDocument();expect(within(screen.getByRole('navigation',{name:'Main navigation'})).getAllByRole('link').map(a=>a.textContent)).toEqual(['Overview','Orders','Payments','Inventory','Carwash','Reports'])});
 it('filters saved inventory',async()=>{open('/store_manager/store-overview');await screen.findByText('Flour',{selector:'td'});fireEvent.change(screen.getByLabelText('Stock status'),{target:{value:'low stock'}});expect(screen.queryByText('Flour',{selector:'td'})).not.toBeInTheDocument();expect(screen.getByText('Tomatoes',{selector:'td'})).toBeInTheDocument()});
 it('creates an ingredient through the correct endpoint and fetches it after remount',async()=>{
 const view=open('/store_manager/store-overview');await screen.findByText('Flour',{selector:'td'});
 fireEvent.change(screen.getByLabelText('Ingredient name'),{target:{value:'Rice'}});fireEvent.change(screen.getByLabelText('Unit'),{target:{value:'kg'}});
 fireEvent.click(screen.getByRole('button',{name:'Save record'}));
 expect(await screen.findByText('Rice',{selector:'td'})).toBeInTheDocument();
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/stock/ingredients'),expect.objectContaining({method:'POST'}));
 view.unmount();open('/store_manager/store-overview');expect(await screen.findByText('Rice',{selector:'td'})).toBeInTheDocument();
 });
 it('keeps form values after a failed save',async()=>{
 open('/store_manager/store-overview');await screen.findByText('Flour',{selector:'td'});
 const original=fetchMock.getMockImplementation();fetchMock.mockImplementation((url,opts)=>opts.method==='POST'?Promise.resolve(response({detail:'Duplicate ingredient'},409)):original(url,opts));
 fireEvent.change(screen.getByLabelText('Ingredient name'),{target:{value:'Rice'}});fireEvent.change(screen.getByLabelText('Unit'),{target:{value:'kg'}});fireEvent.click(screen.getByRole('button',{name:'Save record'}));
 await waitFor(()=>expect(screen.getAllByRole('alert')[0]).toHaveTextContent('Duplicate ingredient'));expect(screen.getByLabelText('Ingredient name')).toHaveValue('Rice');
 });
 it('submits a table order from the touch menu',async()=>{
 open('/waiter/new-order');fireEvent.click(await screen.findByRole('button',{name:/Table 1/}));
 fireEvent.click(await screen.findByRole('button',{name:'Add one Tea'}));fireEvent.click(screen.getByRole('button',{name:'Add one Tea'}));
 fireEvent.click(screen.getByRole('button',{name:'Review order'}));fireEvent.click(screen.getByRole('button',{name:'Submit order'}));
 expect(await screen.findByRole('heading',{name:'Bill B-LIVE-2'})).toBeInTheDocument();
 const call=fetchMock.mock.calls.find(([url,opts])=>url.endsWith('/api/orders')&&opts.method==='POST');
 expect(JSON.parse(call[1].body)).toMatchObject({table_id:1,items:[{menu_item_id:1,quantity:2}]});
 expect(call[1].headers['Idempotency-Key']).toBeTruthy();
 expect(localStorage.getItem('b360_waiter_drafts:1:new')).toBeNull();
 });
 it('calculates cash change and submits the reviewed bill version',async()=>{
 open('/cashier/checkout');fireEvent.click(await screen.findByRole('button',{name:/Table 1.*KES 320/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Record cash payment'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'KES 500'}));
 expect(screen.getByText('Change to return').parentElement).toHaveTextContent('KES 180');
 fireEvent.click(screen.getByRole('button',{name:'Record cash payment'}));
 await screen.findByText('Payment recorded');
 const call=fetchMock.mock.calls.find(([url])=>url.endsWith('/api/orders/1/clear'));
 expect(JSON.parse(call[1].body)).toMatchObject({amount:320,expected_version:1,method:'cash',tendered_amount:500});
 expect(fetchMock.mock.calls.some(([url])=>url.includes('/api/orders?active=true&sort=oldest'))).toBe(true);
 });
 it('requires another review when the selected bill changes',async()=>{
 open('/cashier/checkout');fireEvent.click(await screen.findByRole('button',{name:/Table 1.*KES 320/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Record cash payment'})).toBeEnabled());
 orders[0]={...orders[0],version:2,total:400,items:[{id:1,name:'Tea',quantity:2,subtotal:400}]};
 fireEvent(window,new Event('focus'));
 const review=await screen.findByRole('button',{name:'I reviewed the updated bill'});
 expect(screen.getByRole('button',{name:'Record cash payment'})).toBeDisabled();
 fireEvent.click(review);fireEvent.click(screen.getByRole('button',{name:'Record cash payment'}));
 await screen.findByText('Payment recorded');
 const call=fetchMock.mock.calls.find(([url])=>url.endsWith('/api/orders/1/clear'));
 expect(JSON.parse(call[1].body)).toMatchObject({amount:400,expected_version:2,tendered_amount:400});
 });
 it('retries an uncertain payment with the original idempotency key and tender',async()=>{
 const original=fetchMock.getMockImplementation();let failed=false;
 fetchMock.mockImplementation((url,opts)=>{if(url.endsWith('/api/orders/1/clear')&&!failed){failed=true;return Promise.reject(new TypeError('Connection lost'))}return original(url,opts)});
 open('/cashier/checkout');fireEvent.click(await screen.findByRole('button',{name:/Table 1.*KES 320/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Record cash payment'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'KES 500'}));fireEvent.click(screen.getByRole('button',{name:'Record cash payment'}));
 fireEvent.click(await screen.findByRole('button',{name:'Retry payment'}));
 await screen.findByText('Payment recorded');
 const calls=fetchMock.mock.calls.filter(([url])=>url.endsWith('/api/orders/1/clear'));
 expect(calls).toHaveLength(2);expect(calls[0][1].body).toBe(calls[1][1].body);
 expect(calls[0][1].headers['Idempotency-Key']).toBeTruthy();expect(calls[0][1].headers['Idempotency-Key']).toBe(calls[1][1].headers['Idempotency-Key']);
 });
 it('records cashless payment then confirms the external receipt',async()=>{
 const view=open('/cashier/checkout');await screen.findByRole('button',{name:/Table 1.*KES 320/});
 fireEvent.click(screen.getByRole('button',{name:/Table 1.*KES 320/}));await screen.findByRole('button',{name:'Cash'});await waitFor(()=>expect(screen.getByRole('button',{name:'M-Pesa'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'M-Pesa'}));fireEvent.change(screen.getByLabelText('M-Pesa receipt number'),{target:{value:'REF123'}});fireEvent.click(screen.getByRole('button',{name:'Record cashless payment'}));
 expect(await screen.findByRole('button',{name:'Print pending record'})).toBeInTheDocument();
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/orders/1/clear'),expect.objectContaining({method:'POST'}));
 view.unmount();open('/cashier/payment-ledger');fireEvent.click(await screen.findByRole('button',{name:/B-LIVE-1.*KES 320/}));
 expect(screen.getByRole('button',{name:'Confirm external receipt'})).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox',{name:'I checked the reference and amount.'}));
 fireEvent.click(screen.getByRole('button',{name:'Confirm external receipt'}));await waitFor(()=>expect(screen.queryByRole('button',{name:'Confirm external receipt'})).not.toBeInTheDocument());
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/payments/5/verify'),expect.objectContaining({method:'PUT'}));
 });
 it('renders saved receipt details and sends date filters to the server',async()=>{
 payments=[{id:8,order_id:1,order_number:'B-LIVE-1',receipt:'RCP-000008',amount:320,method:'cash',status:'completed',tendered_amount:500,change_amount:180,snapshot:{business:{business_name:'Saved Restaurant',address:'Nairobi'},items:[{id:1,name:'Original tea',quantity:2,subtotal:320}],tax_summary:{net_amount:275.86,tax_amount:44.14}}}];
 open('/cashier/receipts');fireEvent.click(await screen.findByRole('button',{name:/RCP-000008.*KES 320/}));
 const preview=within(screen.getByRole('region',{name:'Receipt preview'}));
 expect(preview.getByText('Saved Restaurant')).toBeInTheDocument();expect(preview.getByText('2 × Original tea')).toBeInTheDocument();
 expect(preview.getByText('Change returned').parentElement).toHaveTextContent('KES 180');expect(preview.getByText('VAT (16%, included)')).toBeInTheDocument();
 const print=vi.spyOn(window,'print').mockImplementation(()=>{});fireEvent.click(preview.getByRole('button',{name:'Print receipt'}));expect(print).toHaveBeenCalledOnce();print.mockRestore();
 expect(fetchMock.mock.calls.some(([url])=>new URL(url).pathname==='/api/orders/1')).toBe(false);
 fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-09-01'}});fireEvent.change(screen.getByLabelText('To date'),{target:{value:'2026-09-30'}});
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>url.includes('from_date=2026-09-01')&&url.includes('to_date=2026-09-30')&&url.includes('status_filter=completed'))).toBe(true));
 });
 it('searches receipts on the current page and explains missing historical item details',async()=>{
 payments=[{id:8,order_id:1,order_number:'B-LIVE-1',receipt:'RCP-000008',amount:320,method:'cash',status:'completed'}];
 open('/cashier/receipts');fireEvent.click(await screen.findByRole('button',{name:/RCP-000008.*KES 320/}));
 expect(within(screen.getByRole('region',{name:'Receipt preview'})).getByText('Saved item details are unavailable for this older payment.')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Search this page'),{target:{value:'missing-reference'}});
 expect(screen.getByRole('heading',{name:'No matching receipts'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Reset filters'}));expect(screen.getByRole('button',{name:/RCP-000008.*KES 320/})).toBeInTheDocument();
 });
 it('shows an API error rather than invented dashboard figures',async()=>{fetchMock.mockResolvedValue(response({detail:'Server error'},500));open('/director/overview');expect(await screen.findByRole('alert')).toHaveTextContent('Server error');expect(screen.queryByText('KES 1,734')).not.toBeInTheDocument()});
 it('handles unknown paths',()=>{open('/missing/page');expect(screen.getByRole('heading',{name:'Page not found'})).toBeInTheDocument()});
});
