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

function PrivateRoute({ children }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" replace />;
  // Force password change before anything else
  if (user.must_change_password && loc.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return children;
}

function Shell({ children }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  if (loc.pathname === '/login') return children;

  const role = user?.role;
  const can = {
    schemes: ['admin','accounts','sales','auditor'].includes(role),
    invoices: ['admin','accounts','sales'].includes(role),
    tally: ['admin','accounts'].includes(role),
    users: role === 'admin',
    reports: ['admin','accounts','auditor'].includes(role),
  };

  return (
    <div className="app-shell">
      <div className="topbar">
        <h1>Pragati Sales</h1>
        <div className="flex">
          <span className="user">{user?.full_name} · {role}</span>
          <Link to="/account/security" className="user" style={{ marginRight: 12, color: '#fff', textDecoration: 'none', opacity: 0.85 }}>
            Security
          </Link>
          <button onClick={logout}>Logout</button>
        </div>
      </div>
      <nav className="nav">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/gate-entries">Gate Entries</NavLink>
        <NavLink to="/grns">GRN</NavLink>
        {can.schemes  && <NavLink to="/schemes">Schemes</NavLink>}
        {can.invoices && <NavLink to="/invoices">Invoices</NavLink>}
        {can.reports  && <NavLink to="/reports">Reports</NavLink>}
        {can.tally    && <NavLink to="/tally">Tally Sync</NavLink>}
        {can.users    && <NavLink to="/users">Users</NavLink>}
      </nav>
      <div className="content">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/change-password"     element={<PrivateRoute><ChangePassword /></PrivateRoute>} />
        <Route path="/two-factor-setup"    element={<PrivateRoute><TwoFactorSetup /></PrivateRoute>} />
        <Route path="/account/security"    element={<PrivateRoute><AccountSecurity /></PrivateRoute>} />
        <Route path="/"               element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/gate-entries"   element={<PrivateRoute><GateEntries /></PrivateRoute>} />
        <Route path="/gate-entries/new"  element={<PrivateRoute><GateEntryNew /></PrivateRoute>} />
        <Route path="/gate-entries/:id"  element={<PrivateRoute><GateEntryDetail /></PrivateRoute>} />
        <Route path="/grns"           element={<PrivateRoute><GRNs /></PrivateRoute>} />
        <Route path="/grns/new"       element={<PrivateRoute><GRNNew /></PrivateRoute>} />
        <Route path="/grns/:id"       element={<PrivateRoute><GRNDetail /></PrivateRoute>} />
        <Route path="/schemes"        element={<PrivateRoute><Schemes /></PrivateRoute>} />
        <Route path="/schemes/new"    element={<PrivateRoute><SchemeNew /></PrivateRoute>} />
        <Route path="/invoices"       element={<PrivateRoute><Invoices /></PrivateRoute>} />
        <Route path="/tally"          element={<PrivateRoute><TallySync /></PrivateRoute>} />
        <Route path="/users"          element={<PrivateRoute><Users /></PrivateRoute>} />
        <Route path="/reports"        element={<PrivateRoute><Reports /></PrivateRoute>} />
      </Routes>
    </Shell>
  );
}
