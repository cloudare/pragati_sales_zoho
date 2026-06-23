import { Routes, Route, Navigate, NavLink, useLocation, Link } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import ChangePassword from './pages/ChangePassword';
import TwoFactorSetup from './pages/TwoFactorSetup';
import AccountSecurity from './pages/AccountSecurity';
import Dashboard from './pages/Dashboard';
import GateEntries from './pages/GateEntries';
import GateEntryNew from './pages/GateEntryNew';
import GateEntryDetail from './pages/GateEntryDetail';
import GRNs from './pages/GRNs';
import GRNNew from './pages/GRNNew';
import GRNDetail from './pages/GRNDetail';
import Schemes from './pages/Schemes';
import SchemeNew from './pages/SchemeNew';
import Invoices from './pages/Invoices';
import TallySync from './pages/TallySync';
import Users from './pages/Users';
import Reports from './pages/Reports';
import VoucherSeries from './pages/VoucherSeries';
import Approvals from './pages/Approvals';
import Dispatch from './pages/Dispatch';
import MasterSync from './pages/MasterSync';

function PrivateRoute({ children }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && loc.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return children;
}

function Sidebar() {
  const { user } = useAuth();
  const role = user?.role;
  const can = (...roles) => roles.includes(role);
  const links = [
    { section: 'Operations', items: [
      { to: '/',             label: 'Dashboard',   icon: '◯', show: true },
      { to: '/gate-entries', label: 'Gate Entries', icon: '▣', show: true },
      { to: '/grns',         label: 'GRN',         icon: '▤', show: true },
      { to: '/dispatch',     label: 'Dispatch',    icon: '➜',
        show: can('admin','sales','warehouse','accounts') },
    ]},
    { section: 'Sales & Schemes', items: [
      { to: '/schemes',  label: 'Schemes',  icon: '✦',
        show: can('admin','accounts','sales','auditor') },
      { to: '/invoices', label: 'Invoices', icon: '₹',
        show: can('admin','accounts','sales') },
    ]},
    { section: 'Governance', items: [
      { to: '/approvals',     label: 'Approvals',     icon: '✓',
        show: can('admin','accounts','auditor') },
      { to: '/voucher-series',label: 'Voucher Series',icon: '#',
        show: can('admin','accounts') },
      { to: '/reports',       label: 'Reports',       icon: '⊞',
        show: can('admin','accounts','auditor') },
    ]},
    { section: 'Integration', items: [
      { to: '/master-sync', label: 'Master Sync', icon: '⇄',
        show: can('admin','accounts') },
      { to: '/tally',       label: 'Tally',       icon: 'T',
        show: can('admin','accounts') },
    ]},
    { section: 'Admin', items: [
      { to: '/users', label: 'Users', icon: '◉', show: role === 'admin' },
    ]},
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="logo">PS</div>
        <div>
          <div className="title">Pragati Sales</div>
          <div className="subtitle">ERP Workspace</div>
        </div>
      </div>
      {links.map(group => {
        const visible = group.items.filter(i => i.show);
        if (visible.length === 0) return null;
        return (
          <div key={group.section} className="sidebar-section">
            <div className="sidebar-section-title">{group.section}</div>
            <nav className="sidebar-nav">
              {visible.map(it => (
                <NavLink key={it.to} to={it.to} end={it.to === '/'}>
                  <span className="icon">{it.icon}</span>
                  <span className="label">{it.label}</span>
                </NavLink>
              ))}
            </nav>
          </div>
        );
      })}
    </aside>
  );
}

function Topbar({ title }) {
  const { user, logout } = useAuth();
  const initials = (user?.full_name || user?.username || '?').slice(0, 2).toUpperCase();
  return (
    <header className="topbar">
      <div className="page-title">{title}</div>
      <div className="topbar-right">
        <Link to="/account/security" className="user-chip" style={{ textDecoration: 'none' }}>
          <span className="avatar">{initials}</span>
          <span>{user?.full_name} · <strong>{user?.role}</strong></span>
        </Link>
        <button className="btn-secondary btn-sm" onClick={logout}>Sign out</button>
      </div>
    </header>
  );
}

const TITLES = {
  '/': 'Dashboard',
  '/gate-entries': 'Gate Entries',
  '/grns': 'Goods Receipt Notes',
  '/dispatch': 'Dispatch & Picklist',
  '/schemes': 'Schemes',
  '/invoices': 'Invoices',
  '/approvals': 'Approvals',
  '/voucher-series': 'Voucher Series',
  '/reports': 'Reports',
  '/master-sync': 'Master Sync',
  '/tally': 'Tally Sync',
  '/users': 'Users',
  '/account/security': 'Account Security',
  '/change-password': 'Change Password',
  '/two-factor-setup': 'Two-Factor Setup',
};

function Shell({ children }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (loc.pathname === '/login' || !user) return children;

  // Title resolution — exact match or first-segment match
  const seg = '/' + (loc.pathname.split('/')[1] || '');
  const title = TITLES[loc.pathname] || TITLES[seg] || 'Pragati Sales';

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">
        <Topbar title={title} />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/change-password"  element={<PrivateRoute><ChangePassword /></PrivateRoute>} />
        <Route path="/two-factor-setup" element={<PrivateRoute><TwoFactorSetup /></PrivateRoute>} />
        <Route path="/account/security" element={<PrivateRoute><AccountSecurity /></PrivateRoute>} />
        <Route path="/"                 element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/gate-entries"     element={<PrivateRoute><GateEntries /></PrivateRoute>} />
        <Route path="/gate-entries/new" element={<PrivateRoute><GateEntryNew /></PrivateRoute>} />
        <Route path="/gate-entries/:id" element={<PrivateRoute><GateEntryDetail /></PrivateRoute>} />
        <Route path="/grns"             element={<PrivateRoute><GRNs /></PrivateRoute>} />
        <Route path="/grns/new"         element={<PrivateRoute><GRNNew /></PrivateRoute>} />
        <Route path="/grns/:id"         element={<PrivateRoute><GRNDetail /></PrivateRoute>} />
        <Route path="/schemes"          element={<PrivateRoute><Schemes /></PrivateRoute>} />
        <Route path="/schemes/new"      element={<PrivateRoute><SchemeNew /></PrivateRoute>} />
        <Route path="/invoices"         element={<PrivateRoute><Invoices /></PrivateRoute>} />
        <Route path="/tally"            element={<PrivateRoute><TallySync /></PrivateRoute>} />
        <Route path="/users"            element={<PrivateRoute><Users /></PrivateRoute>} />
        <Route path="/reports"          element={<PrivateRoute><Reports /></PrivateRoute>} />
        <Route path="/dispatch"         element={<PrivateRoute><Dispatch /></PrivateRoute>} />
        <Route path="/approvals"        element={<PrivateRoute><Approvals /></PrivateRoute>} />
        <Route path="/voucher-series"   element={<PrivateRoute><VoucherSeries /></PrivateRoute>} />
        <Route path="/master-sync"      element={<PrivateRoute><MasterSync /></PrivateRoute>} />
      </Routes>
    </Shell>
  );
}
