import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import BranchPrinters from '../components/BranchPrinters';

const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=>'application/json'},json:async()=>data});
let calls;
beforeEach(()=>{calls=[];global.fetch=vi.fn(async(url,init={})=>{const path=new URL(url).pathname;calls.push([init.method||'GET',path,init.body&&JSON.parse(init.body)]);
 if(path==='/api/admin/branch-printers'&&init.method==='PUT')return response({id:3});
 if(path==='/api/admin/branch-printers')return response([{id:1,branch:'Westlands',department:'Kitchen',printer_ip:'192.168.2.20',printer_port:9100}]);
 if(path==='/api/branches')return response([{id:1,name:'Main branch',is_active:true},{id:2,name:'Westlands',is_active:true}]);
 if(path==='/api/admin/departments')return response([{id:5,name:'Kitchen'}]);
 return response({},404)})});
afterEach(()=>{cleanup();vi.restoreAllMocks()});

it('sets a printer for one branch and department',async()=>{
 render(<BranchPrinters/>);
 expect(await screen.findByText('192.168.2.20')).toBeTruthy();
 await waitFor(()=>expect(screen.getAllByRole('option',{name:'Westlands'}).length).toBeGreaterThan(0));
 fireEvent.change(screen.getByLabelText('Branch'),{target:{value:'2'}});
 fireEvent.change(screen.getByLabelText('Department'),{target:{value:'5'}});
 fireEvent.change(screen.getByLabelText('Printer IP address (e.g. 192.168.1.50)'),{target:{value:' 192.168.2.21 '}});
 fireEvent.click(screen.getByRole('button',{name:'Save record'}));
 await waitFor(()=>expect(calls).toContainEqual(['PUT','/api/admin/branch-printers',{branch_id:2,department_id:5,printer_ip:'192.168.2.21',printer_port:9100}]));
});
