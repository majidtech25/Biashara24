import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import PrintAgents from '../components/PrintAgents';

const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=>'application/json'},json:async()=>data});
let calls;
beforeEach(()=>{calls=[];global.fetch=vi.fn(async(url,init={})=>{const path=new URL(url).pathname;calls.push([init.method||'GET',path,init.body&&JSON.parse(init.body)]);
 if(path==='/api/print-agents'&&init.method==='POST')return response({id:2,branch:'Westlands',name:'Kitchen PC',key:'bpa_secret123'},201);
 if(path==='/api/print-agents')return response([{id:1,branch:'Main branch',name:'Office PC',is_active:true,online:true,last_seen:'2026-11-24T10:00:00'}]);
 if(path==='/api/branches')return response([{id:1,name:'Main branch'},{id:2,name:'Westlands'}]);
 return response({},404)})});
afterEach(()=>{cleanup();vi.restoreAllMocks()});

it('adds a print program and shows its key once',async()=>{
 render(<PrintAgents/>);
 expect(await screen.findByText('Connected')).toBeTruthy();
 await waitFor(()=>expect(screen.getAllByRole('option',{name:'Westlands'}).length).toBeGreaterThan(0));
 fireEvent.change(screen.getByLabelText('Branch'),{target:{value:'2'}});
 fireEvent.change(screen.getByLabelText('Computer name (e.g. Kitchen PC)'),{target:{value:'Kitchen PC'}});
 fireEvent.click(screen.getByRole('button',{name:'Save record'}));
 expect(await screen.findByText('bpa_secret123')).toBeTruthy();
 expect(calls).toContainEqual(['POST','/api/print-agents',{branch_id:2,name:'Kitchen PC'}]);
 fireEvent.click(screen.getByRole('button',{name:'Done'}));
 expect(screen.queryByText('bpa_secret123')).toBeNull();
});
