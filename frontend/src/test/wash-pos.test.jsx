import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {WashPOS} from '../pages/LiveStockWash';
import {useAction} from '../pages/LiveUI';

const response=data=>({ok:true,status:201,headers:{get:()=>'application/json'},json:async()=>data});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
function POS({onMpesa}){const action=useAction(()=>{});return <WashPOS action={action} onMpesa={onMpesa}/>}

it('records a car wash sale from plate, amount and payment method',async()=>{
 const fetch=vi.fn(async(url,options)=>response({id:9,vehicle_plate:'KDA 123A',amount:450,payment_status:'completed',...JSON.parse(options.body||'{}')}));vi.stubGlobal('fetch',fetch);
 render(<POS onMpesa={()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Number plate'),{target:{value:'kda 123a'}});
 fireEvent.change(screen.getByLabelText('Amount (KES)'),{target:{value:'450'}});
 fireEvent.click(screen.getByRole('button',{name:'Record cash sale'}));
 await waitFor(()=>expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/carwash/transaction'),expect.objectContaining({method:'POST'})));
 expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({vehicle_plate:'KDA 123A',amount:450,payment_method:'cash',pay_later:false});
 expect(await screen.findByRole('status')).toHaveTextContent('paid in cash');
});

it('opens the Paybill step for an M-Pesa sale',async()=>{
 const fetch=vi.fn(async()=>response({id:10,vehicle_plate:'KCB 456B',amount:600,payment_status:'pending'}));vi.stubGlobal('fetch',fetch);
 const onMpesa=vi.fn();render(<POS onMpesa={onMpesa}/>);
 fireEvent.change(screen.getByLabelText('Number plate'),{target:{value:'KCB 456B'}});
 fireEvent.change(screen.getByLabelText('Amount (KES)'),{target:{value:'600'}});
 fireEvent.click(screen.getByRole('button',{name:'M-Pesa'}));
 fireEvent.click(screen.getByRole('button',{name:'Record and show Paybill'}));
 await waitFor(()=>expect(onMpesa).toHaveBeenCalledWith(expect.objectContaining({id:10})));
 expect(JSON.parse(fetch.mock.calls[0][1].body).pay_later).toBe(true);
});
