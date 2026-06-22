import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState({ gateCreated: 0, gateUnloaded: 0, grnsDraft: 0, grnsPushed: 0, schemes: 0 });
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [ge, gu, gd, gp, schemes] = await Promise.all([
          api.get('/api/gate-entries', { params: { status_filter: 'created' } }),
          api.get('/api/gate-entries', { params: { status_filter: 'unloaded' } }),
          api.get('/api/grns', { params: { status_filter: 'draft' } }),
          api.get('/api/grns', { params: { status_filter: 'pushed_to_zoho' } }),
          api.get('/api/schemes', { params: { active_only: true } }).catch(() => ({ data: [] })),
        ]);
        setStats({
          gateCreated: ge.data.length,
          gateUnloaded: gu.data.length,
          grnsDraft: gd.data.length,
          grnsPushed: gp.data.length,
          schemes: schemes.data.length,
        });
        setRecent(ge.data.slice(0, 5));
      } catch {} finally { setLoading(false); }
    })();
  }, []);

  const isGuard = user?.role === 'guard';

  return (
    <div>
      <div className="card">
        <h2>Welcome, {user?.full_name}</h2>
        <div className="muted">{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
      </div>

      {isGuard ? (
        <div className="card">
          <h3>Quick Actions</h3>
          <Link to="/gate-entries/new" className="btn btn-primary btn-full mt">
            + New Gate Entry
          </Link>
          <Link to="/gate-entries" className="btn btn-secondary btn-full mt">
            View Gate Entries
          </Link>
        </div>
      ) : (
        <>
          {loading ? <div className="loading">Loading...</div> : (
            <>
              <div className="form-row">
                <div className="card">
                  <div className="muted small">GATE ENTRIES — OPEN</div>
                  <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--primary)' }}>{stats.gateCreated}</div>
                  <Link to="/gate-entries" className="small">view all →</Link>
                </div>
                <div className="card">
                  <div className="muted small">GRN — DRAFT</div>
                  <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--warning)' }}>{stats.grnsDraft}</div>
                  <Link to="/grns" className="small">view all →</Link>
                </div>
              </div>
              <div className="form-row">
                <div className="card">
                  <div className="muted small">GRN — PUSHED TO ZOHO</div>
                  <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--success)' }}>{stats.grnsPushed}</div>
                </div>
                <div className="card">
                  <div className="muted small">ACTIVE SCHEMES</div>
                  <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--primary)' }}>{stats.schemes}</div>
                  <Link to="/schemes" className="small">view all →</Link>
                </div>
              </div>
            </>
          )}

          {recent.length > 0 && (
            <div className="card">
              <h3>Recent Gate Entries</h3>
              <table className="table">
                <thead><tr><th>Number</th><th>Vehicle</th><th>Vendor</th><th>Status</th></tr></thead>
                <tbody>
                  {recent.map(r => (
                    <tr key={r.id} onClick={() => window.location.href = `/gate-entries/${r.id}`} style={{ cursor: 'pointer' }}>
                      <td>{r.entry_number}</td>
                      <td>{r.vehicle_number}</td>
                      <td>{r.vendor_name}</td>
                      <td><span className={`pill pill-${r.status}`}>{r.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
