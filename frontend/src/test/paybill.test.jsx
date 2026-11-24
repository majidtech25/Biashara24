import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {CustomerBill,PaybillBlock,PaymentsReceived} from '../components/Paybill';

const details={paybill:'600996',account:'B20261124001',amount:320,qr:'iVBORw0KGgo=',qr_note:null,payments:[
 {id:1,receipt:'TKL5ABC123',amount:320,payer:'WANJIKU',status:'received'},
 {id:2,receipt:'TKL5ABC999',amount:320,payer:null,phone:'2547 ***** 678',status:'used'}]};
const response=data=>({ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>data});

beforeEach(()=>{global.fetch=vi.fn(async()=>response({business_name:'Mama Pima Grill',address:'Nairobi'}))});
afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Paybill on the bill',()=>{
 it('shows the Paybill, account, amount and QR code',()=>{
  render(<PaybillBlock details={details}/>);
  const block=screen.getByLabelText('Pay with M-Pesa');
  expect(within(block).getByText('600996')).toBeTruthy();
  expect(within(block).getByText('B20261124001')).toBeTruthy();
  expect(screen.getByAltText('M-Pesa QR code for this bill').getAttribute('src')).toBe('data:image/png;base64,iVBORw0KGgo=');
 });

 it('explains a missing QR code and hides itself with no Paybill',()=>{
  const {rerender}=render(<PaybillBlock details={{...details,qr:null,qr_note:'QR codes appear once the Daraja keys are set up.'}}/>);
  expect(screen.getByText(/Daraja keys/)).toBeTruthy();
  expect(screen.queryByAltText(/QR code/)).toBeNull();
  rerender(<PaybillBlock details={{...details,paybill:null}}/>);
  expect(screen.queryByLabelText('Pay with M-Pesa')).toBeNull();
 });

 it('prints the customer bill with the business name and payment details',async()=>{
  const print=vi.spyOn(window,'print').mockImplementation(()=>{});
  const bill={order_number:'B-2026-1124-001',table_number:4,waiter:'Amina',total:320,items:[{id:1,name:'Tea',quantity:2,subtotal:320}]};
  render(<CustomerBill bill={bill} details={details}/>);
  expect(await screen.findByText('Mama Pima Grill')).toBeTruthy();
  const paper=document.querySelector('.receipt-print-root');
  expect(paper.textContent).toContain('NOT YET PAID');
  expect(paper.textContent).toContain('600996');
  expect(paper.textContent).toContain('B20261124001');
  fireEvent.click(screen.getByRole('button',{name:/Print bill/}));
  expect(print).toHaveBeenCalled();
 });
});

describe('Payments received',()=>{
 it('lets the cashier use a payment Safaricom reported, but not one already used',()=>{
  const onUse=vi.fn();
  render(<PaymentsReceived details={details} onUse={onUse}/>);
  const list=screen.getByRole('region',{name:'M-Pesa payments received'});
  expect(within(list).getByText('Already used')).toBeTruthy();
  const buttons=within(list).getAllByRole('button',{name:'Use this payment'});
  expect(buttons).toHaveLength(1);
  fireEvent.click(buttons[0]);
  expect(onUse).toHaveBeenCalledWith(details.payments[0]);
 });

 it('tells staff where the customer pays when nothing has arrived yet',()=>{
  render(<PaymentsReceived details={{...details,payments:[]}} onUse={()=>{}}/>);
  expect(screen.getByText(/Paybill 600996, account B20261124001/)).toBeTruthy();
 });
});
