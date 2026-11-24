import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import PreviewWorkspace,{Notifications,previewModules} from '../pages/PreviewWorkspace';
import OrderBoard from '../pages/OrderBoard';
import FoodPhoto from '../components/FoodPhoto';
import {Configuration} from '../pages/LiveConfiguration';
vi.mock('../auth/AuthContext',()=>({useAuth:()=>({user:{id:1,role:'manager'}})}));
const reply=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>reply([]))));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
const open=element=>render(<MemoryRouter>{element}</MemoryRouter>);
describe('frontend completion',()=>{
 it.each(Object.keys(previewModules))('renders a dedicated %s preview with view and edit interactions',page=>{
  open(<PreviewWorkspace page={page}/>);
  expect(screen.getByRole('heading',{level:1,name:previewModules[page].title})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Load example'}));
  if(previewModules[page].board)fireEvent.click(screen.getByRole('button',{name:/Example/}));else fireEvent.click(screen.getByRole('button',{name:'View'}));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Edit preview'}));
  expect(screen.getByRole('button',{name:'Save preview'})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Cancel'}));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
 });
 it('saves and searches supplier previews without calling an API, and resets them on remount',()=>{
  const view=open(<PreviewWorkspace page="suppliers"/>);
  fireEvent.click(screen.getByRole('button',{name:'Add supplier'}));
  for(const [label,value] of [['Supplier name','Fresh Foods'],['Contact person','Amina'],['Phone','0712345678']])fireEvent.change(screen.getByLabelText(label),{target:{value}});
  fireEvent.click(screen.getByRole('button',{name:'Save preview'}));
  expect(screen.getByText('Fresh Foods')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Search records'),{target:{value:'missing'}});
  expect(screen.queryByText('Fresh Foods')).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();view.unmount();open(<PreviewWorkspace page="suppliers"/>);
  expect(screen.getByRole('heading',{name:'No suppliers yet'})).toBeInTheDocument();
 });
 it('allows a zero stock count and computes its negative variance',()=>{
  open(<PreviewWorkspace page="stock-counts"/>);fireEvent.click(screen.getByRole('button',{name:'Add stock count'}));
  fireEvent.change(screen.getByLabelText('Count reference'),{target:{value:'COUNT-1'}});
  fireEvent.change(screen.getByLabelText('Count date'),{target:{value:'2026-09-28'}});
  fireEvent.change(screen.getByLabelText('Item 1'),{target:{value:'Rice'}});
  fireEvent.change(screen.getByLabelText('Counted quantity 1'),{target:{value:'0'}});
  fireEvent.change(screen.getByLabelText('Expected quantity 1'),{target:{value:'5'}});
  expect(screen.getByText('Difference: -5 kg')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Save preview'}));expect(screen.getByText('COUNT-1')).toBeInTheDocument();expect(fetch).not.toHaveBeenCalled();
 });
 it('marks preview notifications as read and filters the inbox',()=>{
  open(<Notifications/>);fireEvent.click(screen.getByRole('button',{name:'Load examples'}));
  fireEvent.change(screen.getByLabelText('Notifications filter'),{target:{value:'unread'}});
  fireEvent.click(screen.getByRole('button',{name:'Mark all read'}));
  expect(screen.getByRole('heading',{name:'No unread notifications'})).toBeInTheDocument();expect(fetch).not.toHaveBeenCalled();
 });
 it('opens live kitchen ticket details and sends only the selected status action',async()=>{
  let bill={id:1,order_number:'LIVE-1',table_number:3,status:'printed',waiter:'Amina',total:116,notes:'No chilli',items:[{id:1,name:'Pilau',quantity:1,subtotal:116,department:'Kitchen'}],batches:[]};
  fetch.mockImplementation(async(url,opts)=>{if(opts.method==='PUT'){bill={...bill,status:JSON.parse(opts.body).status};return reply(bill)}return reply([bill])});
  open(<OrderBoard kitchen/>);fireEvent.click(await screen.findByRole('button',{name:/LIVE-1/}));
  const dialog=screen.getByRole('dialog');expect(within(dialog).getByText('No chilli')).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button',{name:'Mark ready'}));
  await waitFor(()=>expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/orders/1'),expect.objectContaining({method:'PUT',body:JSON.stringify({status:'ready'})})));
 });
 it('saves service edits to the live record with a PUT request',async()=>{
  fetch.mockImplementation(async url=>reply(url.includes('/services')?[{id:1,name:'Full wash',price:500,duration_minutes:30,is_active:true}]:[]));
  open(<Configuration resource="services" title="Wash Services"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Edit'}));
  fireEvent.change(within(screen.getByRole('dialog')).getByLabelText('Price'),{target:{value:'600'}});
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}));
  await waitFor(()=>expect(fetch.mock.calls.some(([url,opts])=>opts?.method==='PUT'&&url.includes('/api/carwash/services/1')&&JSON.parse(opts.body).price===600&&JSON.parse(opts.body).is_active===true)).toBe(true));
  expect(screen.queryByRole('heading',{name:'Preview edits — not applied to live records'})).toBeNull();
 });
 it('replaces broken food images with a labelled fallback',()=>{
  render(<FoodPhoto src="https://example.com/missing.jpg" alt="Pilau"/>);fireEvent.error(screen.getByRole('img',{name:'Pilau'}));expect(screen.getByRole('img',{name:'Pilau photo unavailable'})).toBeInTheDocument();
 });
});
