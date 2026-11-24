import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import App from '../App';
import {http} from '../services/http';

const identity=vi.hoisted(()=>({id:1,role:'director',branch_id:null}));
vi.mock('../auth/AuthContext',()=>({AuthProvider:({children})=>children,useAuth:()=>({user:{...identity,username:'boss@example.com'},status:'authenticated',logout:vi.fn()})}));
const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
const branches=[{id:1,name:'Main branch',code:'MAIN',address:'Kilimani',phone:null,is_active:true},{id:2,name:'Westlands',code:'WEST',address:'Westlands',phone:null,is_active:true}];
let mock,reload;
beforeEach(()=>{
 localStorage.clear();identity.role='director';identity.branch_id=null;
 mock=vi.fn(async(url,options={})=>{
  const path=new URL(url).pathname;
  if(path==='/api/branches'&&options.method==='POST')return response({id:3,...JSON.parse(options.body),is_active:true},201);
  if(path==='/api/branches')return response(branches);
  if(path==='/api/branches/2/menu')return response([{menu_item_id:5,name:'Pilau',available:true}]);
  if(path==='/api/branches/2/menu/5')return response({available:false});
  return response([]);
 });
 vi.stubGlobal('fetch',mock);
 reload=vi.fn();vi.stubGlobal('location',{...window.location,reload});
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const open=path=>render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>);

it('lets a director switch the working branch and sends it with every request',async()=>{
 open('/director/branches');
 const picker=await screen.findByRole('combobox',{name:'Working branch'});
 expect(await within(picker).findByRole('option',{name:'Westlands'})).toBeInTheDocument();
 expect(picker).toHaveValue('');
 fireEvent.change(picker,{target:{value:'2'}});
 expect(localStorage.getItem('b360_branch')).toBe('2');
 expect(reload).toHaveBeenCalled();
 await http.get('/api/orders');
 expect(mock).toHaveBeenLastCalledWith(expect.stringContaining('/api/orders'),expect.objectContaining({headers:expect.objectContaining({'X-Branch-Id':'2'})}));
});

it('lists branches, adds one and switches menu items per branch',async()=>{
 open('/director/branches');
 expect(await screen.findByRole('heading',{name:'Branches'})).toBeInTheDocument();
 expect(await screen.findByText('WEST',{selector:'td'})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Branch name'),{target:{value:'Thika Road'}});
 fireEvent.change(screen.getByLabelText(/Short code/),{target:{value:'THIKA'}});
 fireEvent.submit(screen.getByLabelText('Branch name').closest('form'));
 expect(await screen.findByText('Saved successfully.')).toBeInTheDocument();
 expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/branches'),expect.objectContaining({method:'POST',body:expect.stringContaining('THIKA')}));
 const row=screen.getByText('WEST',{selector:'td'}).closest('tr');
 fireEvent.click(within(row).getByRole('button',{name:'Menu availability'}));
 const dialog=await screen.findByRole('dialog',{name:'Menu at Westlands'});
 fireEvent.click(await within(dialog).findByRole('button',{name:'Switch off'}));
 await within(dialog).findByText('Saved successfully.');
 expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/branches/2/menu/5'),expect.objectContaining({method:'PUT',body:JSON.stringify({available:false})}));
});

it('shows staff their own branch without a switcher',async()=>{
 identity.role='manager';identity.branch_id=2;
 open('/manager/branch-menu');
 expect(await screen.findByRole('heading',{name:'Branch menu'})).toBeInTheDocument();
 expect(screen.queryByRole('combobox',{name:'Working branch'})).not.toBeInTheDocument();
 expect((await screen.findAllByText('Westlands')).length).toBeGreaterThan(0);
 expect(await screen.findByText('Pilau')).toBeInTheDocument();
});
