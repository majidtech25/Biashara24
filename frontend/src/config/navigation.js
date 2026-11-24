import {
  LayoutDashboard, ShoppingBag, CreditCard, Boxes, Car, BarChart3, Users,
  Building2, ScrollText, Bell, Settings, ChefHat, UtensilsCrossed, Printer,
  Receipt, WalletCards, ClipboardCheck, Truck, SlidersHorizontal, BookOpen,
  History, PackageSearch, Warehouse, CircleDollarSign, ListChecks, Wrench,
  UserRoundCheck, Gauge, FileBarChart
} from 'lucide-react';

export const roles = {
  kitchen: {label:'Kitchen',nav:[['kitchen','Preparation queue',ChefHat]]},
  director: {
    label: 'Director',
    user: 'Abdul Hared',
    sidebarLinks: ['overview', 'orders', 'payments', 'inventory', 'car-wash', 'reports'],
    extraPages: ['tables', 'bill-changes', 'menu', 'categories', 'departments', 'printers', 'bay-config', 'service-types'],
    nav: [
      ['overview', 'Overview', LayoutDashboard], ['orders', 'Orders', ShoppingBag],
      ['payments', 'Payments', CreditCard], ['inventory', 'Inventory', Boxes],
      ['car-wash', 'Carwash', Car], ['reports', 'Reports', BarChart3],
      ['management', 'Management', Users], ['branches', 'Branches', Building2],
      ['audit', 'Audit Logs', ScrollText], ['notifications', 'Notifications', Bell],
      ['settings', 'System Settings', Settings]
      ,['kitchen','Kitchen Operations',ChefHat],['reorder','Purchasing',Truck],['recipes','Recipes',BookOpen],['suppliers','Suppliers',Users],['deliveries','Stock Documents',Truck],['stock-counts','Stock Counts',ClipboardCheck],['reconciliation','Cash Reconciliation',WalletCards],['refunds','Refunds',Receipt],['printer-recovery','Printer Recovery',Printer]
    ]
  },
  manager: {
    label: 'Manager',
    user: 'Mary Akinyi',
    sidebarLinks: ['manager-dashboard', 'order-pipeline', 'menu', 'staff', 'printers', 'manager-reports'],
    extraPages: ['tables', 'bill-changes', 'categories', 'manager-payments'],
    nav: [
      ['manager-dashboard', 'Manager Dashboard', LayoutDashboard], ['order-pipeline', 'Orders', ListChecks],
      ['kitchen', 'Kitchen Operations', ChefHat], ['menu', 'Menu', UtensilsCrossed],
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
    sidebarLinks: ['checkout', 'pending-bills', 'payment-ledger', 'receipts', 'cashier-carwash', 'shift-summary'],
    nav: [
      ['checkout', 'Checkout', ShoppingBag], ['pending-bills', 'Pending Bills', Receipt],
      ['payment-ledger', 'Payments', CreditCard], ['cash-payment', 'Cash Payment', CircleDollarSign],
      ['mpesa', 'M-Pesa Confirmation', WalletCards], ['receipts', 'Receipts', Receipt],
      ['reconciliation', 'Reconciliation', ClipboardCheck], ['cashier-carwash', 'Car Wash', Car],
      ['shift-summary', 'Shift Summary', BarChart3]
    ]
  },
  store_manager: {
    label: 'Store Manager',
    user: 'Faith Wanjiku',
    sidebarLinks: ['store-overview', 'ingredients', 'receive-stock', 'adjustments', 'stock-history', 'inventory-reports'],
    nav: [
      ['store-overview', 'Inventory Overview', LayoutDashboard], ['ingredients', 'Ingredients', Boxes],
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
    nav: [['bills', 'My bills', Receipt], ['new-order', 'New order', ShoppingBag], ['history', 'History', History],['food-pickup','Food pickup',ChefHat],['notifications','Notifications',Bell]]
  },
  carwash_manager: {
    label: 'Car Wash Manager',
    user: 'Collins Ouma',
    sidebarLinks: ['wash-overview', 'new-wash', 'wash-payments', 'wash-history', 'service-types', 'wash-reports'],
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
