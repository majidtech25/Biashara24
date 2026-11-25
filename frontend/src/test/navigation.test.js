import {describe,expect,it} from 'vitest';
import {roles} from '../config/navigation';
import {workflowFor} from '../config/workflows';

describe('role navigation',()=>{
  it('defines all operational workspaces',()=>expect(Object.keys(roles)).toEqual(['director','manager','cashier','store_manager','waiter','carwash_manager']));
  it('gives every navigation destination a workflow contract',()=>{
    for(const role of Object.values(roles))for(const [id] of role.nav){
      const workflow=workflowFor(id);
      expect(workflow.resource).toBeTruthy();
      expect(workflow.action).toBeTruthy();
      expect(workflow.fields.length).toBeGreaterThan(0);
    }
  });
  it('keeps navigation identifiers unique inside each role',()=>{
    for(const role of Object.values(roles)){const ids=role.nav.map(([id])=>id);expect(new Set(ids).size).toBe(ids.length)}
  });
});

describe('sidebars (Majid, 2026-11-25)',()=>{
  const sidebar=role=>roles[role].sidebarLinks.map(id=>roles[role].nav.find(([page])=>page===id)[1]);
  it('shows the agreed links for each account',()=>{
    expect(sidebar('carwash_manager')).toEqual(['Car Wash Overview','New Transaction','History']);
    expect(sidebar('manager')).toEqual(['Manager Dashboard','Orders','Menu','Reports']);
    expect(sidebar('cashier')).toEqual(['Settle bills','Pending Bills','Receipts','Open / close shift']);
    expect(sidebar('director')).toEqual(['Dashboard','Finance','Reports']);
    expect(sidebar('store_manager')).toEqual(['Dashboard','Inventory']);
  });
  it('has no kitchen account or kitchen screens',()=>{
    expect(roles.kitchen).toBeUndefined();
    for(const role of Object.values(roles))expect(role.nav.map(([id])=>id)).not.toContain('kitchen');
  });
});
