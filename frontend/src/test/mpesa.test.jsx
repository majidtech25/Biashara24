import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import MpesaPrompt,{MpesaAttention} from '../components/MpesaPrompt';

const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=> 'application/json'},json:async()=>data});
let mock,state;
beforeEach(()=>{
 state={status:'waiting',polls:0,unmatched:[{id:9,amount:320,phone:'25471****678',receipt:'TAB123',order_id:4,note:'Paid, but the bill is already closed.'}]};
 mock=vi.fn(async(url,options={})=>{
  const path=new URL(url).pathname;
  if(path==='/api/mpesa/prompts'&&options.method==='POST')return response({id:5,status:'waiting',phone:'25471****678',message:'Waiting for the customer to enter their M-Pesa PIN.'},201);
  if(path==='/api/mpesa/prompts/5'){state.polls++;return response(state.polls>1?{id:5,status:'paid',receipt:'TXY999',message:'Paid. Receipt TXY999.'}:{id:5,status:'waiting',phone:'25471****678',message:'Waiting for the customer to enter their M-Pesa PIN.'})}
  if(path==='/api/mpesa/prompts/5/stop')return response({id:5,status:'failed',message:'Stopped by staff'});
  if(path==='/api/mpesa/prompts'&&url.includes('status=unmatched'))return response(state.unmatched);
  if(path==='/api/mpesa/prompts/9/resolve'){state.unmatched=[];return response({id:9,status:'resolved'})}
  return response({});
 });
 vi.stubGlobal('fetch',mock);
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals()});

it('sends a prompt, follows it and reports the payment once',async()=>{
 vi.useFakeTimers({shouldAdvanceTime:true});
 const onPaid=vi.fn();
 render(<MpesaPrompt target={{order_id:4,expected_version:2}} amount={320} onPaid={onPaid}/>);
 fireEvent.change(screen.getByLabelText("Customer's M-Pesa number"),{target:{value:'0712345678'}});
 fireEvent.click(screen.getByRole('button',{name:/Send M-Pesa prompt · KES 320/}));
 expect(await screen.findByText('Prompt sent to 25471****678')).toBeInTheDocument();
 expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/mpesa/prompts'),expect.objectContaining({method:'POST',body:JSON.stringify({order_id:4,expected_version:2,phone:'0712345678'})}));
 await act(()=>vi.advanceTimersByTimeAsync(3100));
 expect(screen.getByText('Prompt sent to 25471****678')).toBeInTheDocument();
 await act(()=>vi.advanceTimersByTimeAsync(3100));
 expect(await screen.findByText('M-Pesa payment received')).toBeInTheDocument();
 expect(onPaid).toHaveBeenCalledTimes(1);
 expect(onPaid.mock.calls[0][0].receipt).toBe('TXY999');
});

it('lets staff stop waiting and send again',async()=>{
 render(<MpesaPrompt target={{carwash_id:3}} amount={800}/>);
 fireEvent.change(screen.getByLabelText("Customer's M-Pesa number"),{target:{value:'0712345678'}});
 fireEvent.click(screen.getByRole('button',{name:/Send M-Pesa prompt/}));
 fireEvent.click(await screen.findByRole('button',{name:'Stop waiting'}));
 expect(await screen.findByText('Stopped by staff')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:/Send the prompt again/})).toBeEnabled();
});

it('shows managers unmatched payments and records how they were resolved',async()=>{
 render(<MpesaAttention/>);
 expect(await screen.findByText('Paid, but the bill is already closed.')).toBeInTheDocument();
 const resolve=screen.getByRole('button',{name:'Mark as resolved'});
 expect(resolve).toBeDisabled();
 fireEvent.change(screen.getByLabelText('What was done'),{target:{value:'Refunded via reversal'}});
 fireEvent.click(resolve);
 await waitFor(()=>expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/mpesa/prompts/9/resolve'),expect.objectContaining({body:JSON.stringify({note:'Refunded via reversal'})})));
 await waitFor(()=>expect(screen.queryByText('Paid, but the bill is already closed.')).toBeNull());
});
