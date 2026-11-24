import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import App from '../App';
const identity=vi.hoisted(()=>({id:7,role:'waiter'}));
vi.mock('../auth/AuthContext',()=>({AuthProvider:({children})=>children,useAuth:()=>({user:{...identity,username:'waiter@example.com'},status:'authenticated',logout:vi.fn()})}));
const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
let mock,bill,fail,postCount;
beforeEach(()=>{
 localStorage.clear();identity.id=7;identity.role='waiter';fail=false;postCount=0;
 bill={id:11,order_number:'B-11',table_id:1,table_number:1,version:1,total:150,created_at:'2026-09-24T09:00:00',status:'pending',waiter:'My name',items:[{id:21,name:'Tea',menu_item_id:1,quantity:3,unit_price:50,subtotal:150}],batches:[{id:1,kind:'original',created_at:'2026-09-24T09:00:00',items:[{name:'Tea',quantity:3,unit_price:50}],deliveries:[{department_id:1,department:'Kitchen',status:'uncertain'}]}],change_requests:[]};
 mock=vi.fn(async(url,options)=>{
 const path=new URL(url).pathname;
 if(path==='/api/menu')return response([{id:1,name:'Tea',price:50,category:'Drinks'},{id:2,name:'Rice',price:100,category:'Meals'}]);
 if(path==='/api/tables')return response([{id:1,number:1,is_active:true,occupied:false},{id:2,number:2,is_active:true,occupied:true,owner:'Other waiter',mine:false}]);
 if(options.method==='POST'){postCount++;if(fail)throw new TypeError('Connection lost');return response(bill,201)}
 if(path==='/api/orders/11')return response(bill);
 if(path==='/api/orders')return response([bill]);
 return response([],200);
 });vi.stubGlobal('fetch',mock);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()});
const open=path=>render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>);

it('shows a supplied product photo on the menu and in the order cart',async()=>{
 open('/waiter/new-order');
 expect(await screen.findByRole('img',{name:'Tea'})).toHaveAttribute('src',expect.stringContaining('031852.png'));
 fireEvent.click(screen.getByRole('button',{name:'Add one Tea'}));
 expect(document.querySelector('.cart-food-photo')).toHaveAttribute('src',expect.stringContaining('031852.png'));
});

it('keeps an unconfigured restaurant on the live workflow instead of simulating orders',async()=>{
 const original=mock.getMockImplementation();
 mock.mockImplementation((url,opts)=>['/api/menu','/api/tables'].includes(new URL(url).pathname)?Promise.resolve(response([])):original(url,opts));
 open('/waiter/new-order?demo=1');
 expect(await screen.findByText('No tables configured. Ask your manager to add tables.')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Review order'})).toBeDisabled();
 expect(screen.queryByText('Demo ordering')).not.toBeInTheDocument();
 expect(screen.queryByText(/Simulat/)).not.toBeInTheDocument();
 expect(postCount).toBe(0);
});

it('submits through the live API even when an old demo link is opened',async()=>{
 open('/waiter/new-order?demo=1');await selectCart();
 fireEvent.click(screen.getByRole('button',{name:'Review order'}));
 fireEvent.click(screen.getByRole('button',{name:'Submit order'}));
 expect(await screen.findByRole('heading',{name:'Bill B-11'})).toBeInTheDocument();
 expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/orders'),expect.objectContaining({method:'POST',headers:expect.objectContaining({'Idempotency-Key':expect.any(String)})}));
});
async function selectCart(){fireEvent.click(await screen.findByRole('button',{name:/Table 1/}));fireEvent.click(await screen.findByRole('button',{name:'Add one Tea'}));fireEvent.change(screen.getByLabelText('Kitchen notes'),{target:{value:'No sugar'}})}

it('shows service navigation, original items, elapsed time and honest delivery wording',async()=>{
 open('/waiter/bills');expect(await screen.findByText('B-11')).toBeInTheDocument();
 expect(within(screen.getByRole('navigation',{name:'Main navigation'})).getAllByRole('link').map(x=>x.textContent)).toEqual(['My bills','New order','History','Food pickup','Notifications']);
 expect(screen.getByText('3 × Tea')).toBeInTheDocument();expect(screen.getByText(/Delivery uncertain\/failed/)).toBeInTheDocument();
 expect(mock).toHaveBeenCalledWith(expect.stringContaining('active=true&sort=oldest&limit=100&offset=0'),expect.anything());
});

it('preserves cart on navigation and isolates drafts by signed-in account',async()=>{
 const view=open('/waiter/new-order');await selectCart();
 fireEvent.click(screen.getByRole('link',{name:'My bills'}));await screen.findByText('B-11');
 fireEvent.click(within(screen.getByRole('navigation',{name:'Main navigation'})).getByRole('link',{name:'New order'}));
 expect(await screen.findByLabelText('Tea quantity')).toHaveTextContent('1');expect(screen.getByLabelText('Kitchen notes')).toHaveValue('No sugar');
 view.unmount();identity.id=8;open('/waiter/new-order');
 expect(await screen.findByLabelText('Tea quantity')).toHaveTextContent('0');expect(screen.getByLabelText('Kitchen notes')).toHaveValue('');
});

it('retries an uncertain submission with exactly the same key and payload after remount',async()=>{
 fail=true;const view=open('/waiter/new-order');await selectCart();fireEvent.click(screen.getByRole('button',{name:'Review order'}));fireEvent.click(screen.getByRole('button',{name:'Submit order'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost');
 expect(screen.getByRole('button',{name:'Add one Tea'})).toBeDisabled();
 const first=mock.mock.calls.find(([,o])=>o.method==='POST')[1];
 view.unmount();fail=false;open('/waiter/new-order');fireEvent.click(await screen.findByRole('button',{name:'Retry submission'}));
 expect(await screen.findByRole('heading',{name:'Bill B-11'})).toBeInTheDocument();
 const calls=mock.mock.calls.filter(([,o])=>o.method==='POST');
 expect(calls[1][1].headers['Idempotency-Key']).toBe(first.headers['Idempotency-Key']);expect(calls[1][1].body).toBe(first.body);
 expect(postCount).toBe(2);expect(localStorage.getItem('b360_waiter_drafts:7:new')).toBeNull();
});

it('prevents unavailable tables, requires items, and filters menu by category',async()=>{
 open('/waiter/new-order');
 expect(await screen.findByRole('button',{name:/Table 2/})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Review order'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Meals',exact:true}));
 expect(screen.queryByRole('button',{name:'Add one Tea'})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Search menu'),{target:{value:'rice'}});
 expect(screen.getByRole('button',{name:'Add one Rice'})).toBeInTheDocument();
});

it('starts additions empty and sends only the newly selected items with the current version',async()=>{
 open('/waiter/new-order?bill=11');
 expect(await screen.findByLabelText('Tea quantity')).toHaveTextContent('0');
 await screen.findByText('Current bill: KES 150');
 fireEvent.click(screen.getByRole('button',{name:'Add one Rice'}));
 expect(screen.getByText('Estimated revised total: KES 250')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Review addition'}));fireEvent.click(screen.getByRole('button',{name:'Send additional items'}));
 await screen.findByRole('heading',{name:'Bill B-11'});
 const call=mock.mock.calls.find(([,o])=>o.method==='POST');
 expect(call[0]).toContain('/api/orders/11/items');
 expect(JSON.parse(call[1].body)).toEqual({expected_version:1,items:[{menu_item_id:2,quantity:1}],notes:''});
});

it('refreshes on focus without overwriting an unsent cart',async()=>{
 open('/waiter/new-order');await selectCart();const before=mock.mock.calls.length;
 fireEvent(window,new Event('focus'));await waitFor(()=>expect(mock.mock.calls.length).toBeGreaterThan(before));
 expect(screen.getByLabelText('Tea quantity')).toHaveTextContent('1');expect(screen.getByLabelText('Kitchen notes')).toHaveValue('No sugar');
});

it('refreshes every 15 seconds while visible',async()=>{
 vi.useFakeTimers();open('/waiter/bills');
 await act(async()=>{});const before=mock.mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000)});
 expect(mock.mock.calls.length).toBeGreaterThan(before);
});

it('shows connection errors with retry and recovers without inventing bills',async()=>{
 const original=mock.getMockImplementation();let failed=false;
 mock.mockImplementation((url,options)=>new URL(url).pathname==='/api/orders'&&!failed?(failed=true,Promise.reject(new TypeError('No connection'))):original(url,options));
 open('/waiter/bills');
 expect(await screen.findByRole('alert')).toHaveTextContent('No connection');
 fireEvent.click(screen.getByRole('button',{name:'Retry'}));expect(await screen.findByText('B-11')).toBeInTheDocument();
});

it('reviews the table, quantities and notes before any order is sent',async()=>{
 open('/waiter/new-order');await selectCart();
 fireEvent.click(screen.getByRole('button',{name:'Review order'}));
 const review=screen.getByRole('dialog',{name:'Review order'});
 expect(within(review).getByText('Table 1')).toBeInTheDocument();
 expect(within(review).getByText('No sugar')).toBeInTheDocument();
 expect(within(review).getByText(/1 \u00d7 Tea/)).toBeInTheDocument();
 expect(postCount).toBe(0);
 fireEvent.click(within(review).getByRole('button',{name:'Edit order'}));
 expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Remove Tea from cart'}));
 expect(screen.getByRole('button',{name:'Review order'})).toBeDisabled();
 expect(postCount).toBe(0);
});

it('opens a cart panel from View order and lets the waiter edit unsent quantities',async()=>{
 open('/waiter/new-order');await selectCart();
 fireEvent.click(screen.getByRole('button',{name:/View order/}));
 const cart=screen.getByRole('dialog',{name:'Current order'});
 fireEvent.click(within(cart).getByRole('button',{name:'Add one Tea in cart'}));
 expect(within(cart).getByLabelText('Tea quantity in cart')).toHaveTextContent('2');
 fireEvent.click(within(cart).getByRole('button',{name:'Review order'}));
 expect(screen.getByRole('dialog',{name:'Review order'})).toHaveTextContent('2 \u00d7 Tea');
 expect(postCount).toBe(0);
});

it('shows an empty search state and clears filters',async()=>{
 open('/waiter/new-order');await screen.findByRole('button',{name:'Add one Tea'});
 fireEvent.change(screen.getByLabelText('Search menu'),{target:{value:'does not exist'}});
 expect(screen.getByText('No matching items')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Clear filters'}));
 expect(screen.getByRole('button',{name:'Add one Tea'})).toBeInTheDocument();
});

it('explains why review is disabled before a table and items are selected',async()=>{
 open('/waiter/new-order');await screen.findByRole('button',{name:'Add one Tea'});
 expect(screen.getByRole('button',{name:'Review order'})).toHaveAccessibleDescription('Select an available table before reviewing your order.');
 fireEvent.click(screen.getByRole('button',{name:/Table 1/}));
 expect(screen.getByRole('button',{name:'Review order'})).toHaveAccessibleDescription('Add at least one food or drink before reviewing your order.');
 fireEvent.click(screen.getByRole('button',{name:'Add one Tea'}));
 expect(screen.getByRole('button',{name:'Review order'})).toBeEnabled();
});

it('explains a table becoming occupied and lets the waiter choose another table',async()=>{
 open('/waiter/new-order');await selectCart();
 const original=mock.getMockImplementation();
 mock.mockImplementation((url,opts)=>new URL(url).pathname==='/api/tables'?Promise.resolve(response([
  {id:1,number:1,is_active:true,occupied:true,mine:false},
  {id:3,number:3,is_active:true,occupied:false}
 ])):original(url,opts));
 fireEvent(window,new Event('focus'));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Review order'})).toHaveAccessibleDescription('This table is now occupied. Choose another available table.'));
 fireEvent.click(screen.getByRole('button',{name:'Choose another table'}));
 fireEvent.click(screen.getByRole('button',{name:/Table 3/}));
 expect(screen.getByRole('button',{name:'Review order'})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'Review order'}));
 expect(screen.getByRole('dialog',{name:'Review order'})).toHaveTextContent('Table 3');
});

it('sends a takeaway order without a table',async()=>{
 open('/waiter/new-order');
 fireEvent.click(await screen.findByRole('button',{name:/Takeaway/}));
 fireEvent.change(screen.getByLabelText('Customer name (optional)'),{target:{value:'Amina'}});
 fireEvent.click(await screen.findByRole('button',{name:'Add one Tea'}));
 expect(screen.getAllByText('Takeaway · Amina').length).toBeGreaterThan(0);
 fireEvent.click(screen.getByRole('button',{name:'Review order'}));
 fireEvent.click(screen.getByRole('button',{name:'Submit order'}));
 await screen.findByRole('heading',{name:'Bill B-11'});
 const post=mock.mock.calls.find(([url,o])=>o?.method==='POST'&&new URL(url).pathname==='/api/orders');
 const body=JSON.parse(post[1].body);
 expect(body).toMatchObject({order_type:'takeaway',customer:'Amina',items:[{menu_item_id:1,quantity:1}]});
 expect(body.table_id).toBeUndefined();
});
