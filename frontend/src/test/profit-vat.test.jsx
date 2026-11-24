import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import {ProfitVat} from '../pages/LiveReports';

const report={restaurant:{sales_gross:1160,sales_vat:160,refunds_gross:116,refunds_vat:16,net_sales:900,food_cost:200,gross_profit:700,gross_margin_percent:77.8,stock_written_off:50,profit_after_write_offs:650,bills_paid:1},
 vat:{rates:[{rate:16,gross:1160,vat:160,net:1000}],sales_vat:160,credit_note_vat:16,vat_due:144,sales_without_rate:0},
 carwash:{revenue:800,note:'Car wash prices have no VAT rate recorded in the system.'},
 items:[{item:'Nyama choma',quantity:2,gross:1160,net:1000,food_cost:200,gross_profit:800,units_without_cost:0}],
 notes:{units_without_cost:3,estimated_cost_lines:0}};
const response=data=>({ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>data});
let urls;
beforeEach(()=>{urls=[];global.fetch=vi.fn(async url=>{urls.push(String(url));return response(report)})});
afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Profit and VAT report',()=>{
 it('shows profit, VAT due, VAT by rate and profit by dish for the period',async()=>{
  render(<ProfitVat from="2026-11-01" to="2026-11-24"/>);
  expect(await screen.findByText('Nyama choma')).toBeTruthy();
  expect(urls.some(u=>u.includes('/api/reports/profit-vat?from_date=2026-11-01&to_date=2026-11-24'))).toBe(true);
  expect(screen.getByText('Gross profit',{selector:'span,small,p,div,dt,strong'})).toBeTruthy();
  expect(screen.getAllByText(/77\.8%/).length).toBeGreaterThan(0);
  const rates=screen.getByRole('heading',{name:'VAT by rate'}).nextElementSibling;
  expect(within(rates).getByText('16%')).toBeTruthy();
  expect(screen.getByText(/3 dish\(es\) sold have no food cost/)).toBeTruthy();
  expect(screen.getByText(/Car wash takings/).textContent).toContain('no VAT rate');
 });
});
