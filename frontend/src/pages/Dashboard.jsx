import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState({});
  const [recent, setRecent] = useState({ gate: [], grns: [], dispatch: [] });
  const [err, setErr] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [g, n, d] = await Promise.all([
          api.get('/api/gate-entries?limit=5').catch(() => ({ data: [] })),
          api.get('/api/grns?limit=5').catch(() => ({ data: [] })),
          api.get('/api/dispatch?limit=5').catch(() => ({ data: [] })),
        ]);
        setRecent({ gate: g.data, grns: n.data, dispatch: d.data });
        setStats({
          gateOpen:    g.data.filter(x => x.status === 'created' || x.status === 'in_progress').length,
          grnOpen:     n.data.filter(x => x.status === 'draft' || x.status === 'submitted').length,
          dispatchActive: d.data.filter(x => x.status !== 'closed' && x.status !== 'cancelled').length,
        });
      } catch (e) { setErr(e.response?.data?.detail || String(e)); }
    })();
  }, []);

  return (
    <>
      <h2 className="mt-0 mb-md">Welcome back, {user?.full_name?.split(' ')[0]}</h2>
      {err && <div className="alert alert-error">{err}</div>}

      <div className="stat-grid mb-md">
        <div className="stat-card">
          <div className="label">Gate Entries (open)</div>
          <div className="value">{stats.gateOpen ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="label">GRNs in progress</div>
          <div className="value">{stats.grnOpen ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="label">Active dispatches</div>
          <div className="value">{stats.dispatchActive ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="label">Your role</div>
          <div className="value" style={{ fontSize: 18, textTransform: 'capitalize' }}>{user?.role}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <RecentCard title="Recent Gate Entries" linkTo="/gate-entries" rows={recent.gate}
          render={(r) => (
            <>
              <td><Link to={`/gate-entries/${r.id}`}>{r.entry_number}</Link></td>
              <td>{r.vendor_name}</td>
              <td><span className={`pill ${r.status === 'closed' ? 'pill-success' : 'pill-warning'}`}>{r.status}</span></td>
            </>
          )}
          cols={['Number', 'Vendor', 'Status']}
        />
        <RecentCard title="Recent GRNs" linkTo="/grns" rows={recent.grns}
          render={(r) => (
            <>
              <td><Link to={`/grns/${r.id}`}>{r.grn_number}</Link></td>
              <td>{r.vendor_name}</td>
              <td><span className={`pill ${r.status === 'closed' ? 'pill-success' : 'pill-warning'}`}>{r.status}</span></td>
            </>
          )}
          cols={['Number', 'Vendor', 'Status']}
        />
        <RecentCard title="Recent Dispatches" linkTo="/dispatch" rows={recent.dispatch}
          render={(r) => (
            <>
              <td>{r.dispatch_number}</td>
              <td>{r.party_name}</td>
              <td><span className={`pill ${r.status === 'closed' ? 'pill-success' : 'pill-warning'}`}>{r.status}</span></td>
            </>
          )}
          cols={['Number', 'Party', 'Status']}
        />
      </div>
    </>
  );
}

function RecentCard({ title, linkTo, rows, render, cols }) {
  return (
    <div className="card">
      <div className="card-header">
        <h3>{title}</h3>
        <Link to={linkTo} className="btn-ghost btn-sm">View all →</Link>
      </div>
      <div className="card-body tight">
        <table className="data">
          <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={cols.length} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                No records yet
              </td></tr>
            ) : rows.map((r, i) => <tr key={r.id || i}>{render(r)}</tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
