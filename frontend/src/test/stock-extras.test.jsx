import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {ExpiringStock,IngredientEditor,LineExtras,lineBody} from '../components/StockExtras';

const response=(data,status=200)=>({ok:status<400,status,headers:{get:()=>'application/json'},json:async()=>data});
let calls;
const flour={id:4,name:'Flour',unit:'kg',cost_per_unit:90,min_level:10,reorder_quantity:100,packs:[{id:1,name:'50 kg bag',factor:50}]};
beforeEach(()=>{calls=[];global.fetch=vi.fn(async(url,init={})=>{const path=new URL(url).pathname;calls.push([init.method||'GET',path,init.body&&JSON.parse(init.body)]);
 if(path==='/api/stock/expiry')return response([{id:1,ingredient_id:5,ingredient:'Milk',unit:'litre',remaining:6,expiry_date:'2026-11-22',days_left:-2,status:'expired',value:600},{id:2,ingredient_id:5,ingredient:'Milk',unit:'litre',remaining:4,expiry_date:'2026-11-26',days_left:2,status:'expiring',value:400}]);
 if(path.endsWith('/packs')&&init.method==='POST')return response({...flour,packs:[...flour.packs,{id:2,name:'2 kg packet',factor:2}]},201);
 if(path==='/api/stock/ingredients/4')return response({...flour,...JSON.parse(init.body||'{}')});
 return response({},404)})});
afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Stock extras',()=>{
 it('lists expired and expiring batches',async()=>{
  render(<ExpiringStock/>);
  expect(await screen.findByText(/1 batch has expired/)).toBeTruthy();
  expect(screen.getByText('Expired 2 day(s) ago')).toBeTruthy();
  expect(screen.getByText('6 litre')).toBeTruthy();
 });

 it('edits cost and adds a pack',async()=>{
  const onClose=vi.fn();
  render(<IngredientEditor ingredient={flour} onClose={onClose} onSaved={()=>{}}/>);
  expect(screen.getByText('1 50 kg bag = 50 kg')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Pack name'),{target:{value:'2 kg packet'}});
  fireEvent.change(screen.getByLabelText('kg in one pack'),{target:{value:'2'}});
  fireEvent.click(screen.getByRole('button',{name:'Add pack'}));
  expect(await screen.findByText('1 2 kg packet = 2 kg')).toBeTruthy();
  expect(calls).toContainEqual(['POST','/api/stock/ingredients/4/packs',{name:'2 kg packet',factor:2}]);
  fireEvent.change(screen.getByLabelText('Cost per kg (KES)'),{target:{value:'95'}});
  fireEvent.click(screen.getByRole('button',{name:'Save'}));
  await waitFor(()=>expect(onClose).toHaveBeenCalled());
  expect(calls).toContainEqual(['PUT','/api/stock/ingredients/4',{cost_per_unit:95,min_level:10,reorder_quantity:100}]);
 });

 it('offers packs, price and expiry on delivery lines only where they apply',()=>{
  const update=vi.fn();
  const {rerender}=render(<LineExtras index={0} kind="receiving" ingredient={flour} line={{pack:'50 kg bag'}} update={update}/>);
  expect(screen.getByLabelText('Price per 50 kg bag (KES) 1')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Expiry date 1'),{target:{value:'2027-01-31'}});
  expect(update).toHaveBeenCalledWith({expiry_date:'2027-01-31'});
  rerender(<LineExtras index={0} kind="wastage" ingredient={flour} line={{}} update={update}/>);
  expect(screen.queryByLabelText(/Price per/)).toBeNull();
  expect(screen.queryByLabelText(/Expiry date/)).toBeNull();
  expect(screen.getByLabelText('Entered in 1')).toBeTruthy();
  expect(lineBody({ingredient_id:'4',quantity:'2',pack:'50 kg bag',unit_cost:'4500',expiry_date:''})).toEqual({ingredient_id:4,quantity:2,pack:'50 kg bag',unit_cost:4500});
  expect(lineBody({ingredient_id:'4',quantity:'3',pack:'',unit_cost:''})).toEqual({ingredient_id:4,quantity:3});
 });
});
