import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import App from '../App';

vi.mock('../auth/AuthContext',()=>({AuthProvider:({children})=>children,useAuth:()=>({user:{id:7,role:'carwash_manager',branch_id:1,username:'wash@example.com'},status:'authenticated',logout:vi.fn()})}));
const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
const wash={id:11,transaction_number:'CW-1',vehicle_plate:'KDA 123A',vehicle_type:'Saloon',service_name:'Full wash',amount:500,payment_status:'completed',wash_status:'waiting',attendant:null,attendant_id:null,created_at:new Date().toISOString(),wash_started_at:null};
let mock,board;
beforeEach(()=>{
 board=[{id:1,bay_number:1,name:'Front',status:'waiting',wash:{...wash}},{id:2,bay_number:2,name:'Back',status:'free',wash:null}];
 mock=vi.fn(async(url,options={})=>{
  const path=new URL(url).pathname;
  if(path==='/api/carwash/board')return response(board);
  if(path==='/api/carwash/attendants'&&options.method==='POST')return response({id:4,...JSON.parse(options.body),is_active:true},201);
  if(path==='/api/carwash/attendants')return response([{id:3,name:'Otieno',phone:'0700',is_active:true},{id:5,name:'Away',phone:null,is_active:false}]);
  if(path==='/api/carwash/11/wash'){const body=JSON.parse(options.body);board[0]={...board[0],status:body.status==='done'?'free':'washing',wash:body.status==='done'?null:{...wash,wash_status:'washing',attendant:'Otieno',attendant_id:3,wash_started_at:new Date().toISOString()}};return response({...wash,wash_status:body.status})}
  return response([]);
 });
 vi.stubGlobal('fetch',mock);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const open=path=>render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>);

it('starts a waiting wash with an attendant and finishes it from the bay board',async()=>{
 open('/carwash_manager/active-bays');
 const bay=await screen.findByRole('article',{name:'Bay 1'});
 expect(within(bay).getByText('KDA 123A · Saloon')).toBeInTheDocument();
 expect(screen.getByRole('article',{name:'Bay 2'})).toHaveTextContent('Ready for the next car');
 fireEvent.click(within(bay).getByRole('button',{name:'Start wash'}));
 const select=await screen.findByRole('combobox',{name:'Attendant'});
 expect(within(select).queryByRole('option',{name:'Away'})).toBeNull();
 fireEvent.change(select,{target:{value:'3'}});
 fireEvent.click(screen.getAllByRole('button',{name:'Start wash'}).at(-1));
 await waitFor(()=>expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/carwash/11/wash'),expect.objectContaining({method:'PUT',body:JSON.stringify({status:'washing',attendant_id:3})})));
 const washing=await screen.findByRole('button',{name:'Finish wash'});
 expect(screen.getByRole('article',{name:'Bay 1'})).toHaveTextContent('Otieno');
 fireEvent.click(washing);
 await waitFor(()=>expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/carwash/11/wash'),expect.objectContaining({body:JSON.stringify({status:'done'})})));
 await waitFor(()=>expect(screen.getByRole('article',{name:'Bay 1'})).toHaveTextContent('Ready for the next car'));
});

it('lists and adds car-wash attendants',async()=>{
 open('/carwash_manager/attendants');
 expect(await screen.findByText('Otieno')).toBeInTheDocument();
 expect(screen.getByText('Inactive')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Full name'),{target:{value:'Wanjiru'}});
 fireEvent.submit(screen.getByLabelText('Full name').closest('form'));
 await waitFor(()=>expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/carwash/attendants'),expect.objectContaining({method:'POST',body:JSON.stringify({name:'Wanjiru',phone:null})})));
});
