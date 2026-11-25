import {
  LayoutDashboard, ShoppingBag, CreditCard, Boxes, Car, BarChart3, Users,
  Building2, ScrollText, Bell, Settings, ChefHat, UtensilsCrossed, Printer,
  Receipt, WalletCards, ClipboardCheck, Truck, SlidersHorizontal, BookOpen,
  History, PackageSearch, Warehouse, CircleDollarSign, ListChecks, Wrench,
  UserRoundCheck, Gauge, FileBarChart
} from 'lucide-react';

export const roles = {
  director: {
    label: 'Director',
    user: 'Abdul Hared',
    sidebarLinks: ['overview', 'payments', 'reports'],  // Majid, 2026-11-25: dashboard, finance, reports
    extraPages: ['tables', 'bill-changes', 'menu', 'categories', 'departments', 'printers', 'bay-config', 'service-types'],
    nav: [
      ['overview', 'Dashboard', LayoutDashboard], ['orders', 'Orders', ShoppingBag],
      ['payments', 'Finance', CreditCard], ['inventory', 'Inventory', Boxes],
      ['car-wash', 'Carwash', Car], ['reports', 'Reports', BarChart3],
      ['management', 'Management', Users], ['branches', 'Branches', Building2],
      ['audit', 'Audit Logs', ScrollText], ['notifications', 'Notifications', Bell],
      ['settings', 'System Settings', Settings]
      ,['reorder','Purchasing',Truck],['recipes','Recipes',BookOpen],['suppliers','Suppliers',Users],['deliveries','Stock Documents',Truck],['stock-counts','Stock Counts',ClipboardCheck],['reconciliation','Cash Reconciliation',WalletCards],['refunds','Refunds',Receipt],['printer-recovery','Printer Recovery',Printer]
    ]
  },
  manager: {
    label: 'Manager',
    user: 'Mary Akinyi',
    sidebarLinks: ['manager-dashboard', 'order-pipeline', 'menu', 'manager-reports'],  // Majid, 2026-11-25
    extraPages: ['tables', 'bill-changes', 'categories', 'manager-payments'],
    nav: [
      ['manager-dashboard', 'Manager Dashboard', LayoutDashboard], ['order-pipeline', 'Orders', ListChecks],
      ['menu', 'Menu', UtensilsCrossed],
      ['staff', 'Staff', Users], ['printers', 'Printers', Printer],
      ['departments', 'Departments', Building2], ['manager-reports', 'Reports', FileBarChart],
      ['branch-menu', 'Branch menu', SlidersHorizontal],
      ['manager-notifications', 'Notifications', Bell]
      ,['reorder','Purchasing',Truck],['recipes','Recipes',BookOpen],['suppliers','Suppliers',Users],['deliveries','Stock Documents',Truck],['stock-counts','Stock Counts',ClipboardCheck],['reconciliation','Cash Reconciliation',WalletCards],['refunds','Refunds',Receipt],['printer-recovery','Printer Recovery',Printer],['settings','Business Settings',Settings]
    ]
  },
  cashier: {
    label: 'Cashier',
    user: 'Hassan Ali',
    // Majid, 2026-11-25: cashiers settle bills, see pending bills, print receipts and open/close their shift.
    // They do not see or print sales or shift summaries.
    sidebarLinks: ['checkout', 'pending-bills', 'receipts', 'reconciliation'],
    extraPages: ['payment-ledger'],  // confirming an M-Pesa payment is part of settling a bill
    nav: [
      ['checkout', 'Settle bills', ShoppingBag], ['pending-bills', 'Pending Bills', Receipt],
      ['receipts', 'Receipts', Receipt], ['reconciliation', 'Open / close shift', ClipboardCheck]
    ]
  },
  store_manager: {
    label: 'Store Manager',
    user: 'Faith Wanjiku',
    sidebarLinks: ['store-overview', 'ingredients'],  // Majid, 2026-11-25: dashboard, inventory
    nav: [
      ['store-overview', 'Dashboard', LayoutDashboard], ['ingredients', 'Inventory', Boxes],
      ['receive-stock', 'Receive Stock', Truck], ['adjustments', 'Adjustments', SlidersHorizontal],
      ['recipes', 'Recipes', BookOpen], ['suppliers', 'Suppliers', Users],
      ['deliveries', 'Deliveries', Warehouse], ['stock-counts', 'Stock Counts', ClipboardCheck],
      ['stock-history', 'Stock History', History], ['low-stock', 'Low Stock', PackageSearch],
      ['reorder', 'Reorder Planning', ListChecks], ['inventory-reports', 'Reports', BarChart3]
    ]
  },
  waiter: {
    label: 'Waiter',
    extraPages: ['orders'],
    nav: [['bills', 'My bills', Receipt], ['new-order', 'New order', ShoppingBag], ['history', 'History', History],['notifications','Notifications',Bell]]
  },
  carwash_manager: {
    label: 'Car Wash Manager',
    user: 'Collins Ouma',
    sidebarLinks: ['wash-overview', 'new-wash', 'wash-history'],  // Majid, 2026-11-25
    nav: [
      ['wash-overview', 'Car Wash Overview', LayoutDashboard], ['active-bays', 'Active Bays', Gauge],
      ['new-wash', 'New Transaction', Car], ['wash-payments', 'Payments', CreditCard],
      ['attendants', 'Staff & Attendants', UserRoundCheck], ['service-types', 'Service Types', Wrench],
      ['wash-history', 'History', History], ['pending-wash-payments', 'Pending Payments', Receipt],
      ['wash-summary', 'Daily Summary', BarChart3], ['wash-reports', 'Reports', FileBarChart],
      ['bay-config', 'Bay Configuration', Settings]
    ]
  }
};

export const firstPage = role => roles[role]?.nav[0][0] || 'overview';
