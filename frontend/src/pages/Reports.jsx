import { useState, useEffect } from 'react';
import { api, API_BASE } from '../api/client';

export default function Reports() {
  const [days, setDays] = useState(30);
  const [byBrand, setByBrand] = useState([]);
  const [schemeUsage, setSchemeUsage] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [u, b] = await Promise.all([
        api.get(`/api/reports/scheme-usage?days=${days}`).catch(() => ({ data: [] })),
        api.get(`/api/reports/scheme-usage/by-brand?days=${days}`).catch(() => ({ data: [] })),
      ]);
      setSchemeUsage(u.data); setByBrand(b.data);
    } catch (e) { setError(e.response?.data?.detail || String(e)); }
    setLoading(false);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [days]);

  const exportExcel = async () => {
    try {
      const r = await api.get(`/api/reports/scheme-usage/export?days=${days}`,
        { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `scheme_usage_${days}d.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(e.response?.data?.detail || 'Export failed'); }
  };

  return (
    <>
      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        <div className="card-header">
          <h3>Scheme Reporting (M4)</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label className="text-small mb-0">Period:</label>
            <select value={days} onChange={e => setDays(+e.target.value)} style={{ width: 120 }}>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            <button className="btn-primary btn-sm" onClick={exportExcel}>↓ Export Excel</button>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16 }}>
        <div className="card">
          <div className="card-header"><h3>By Brand</h3></div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr>
                <th>Brand</th>
                <th className="text-right">Applications</th>
                <th className="text-right">Discount ₹</th>
              </tr></thead>
              <tbody>
                {byBrand.map((b, i) => (
                  <tr key={i}>
                    <td>{b.brand}</td>
                    <td className="text-right">{b.applications}</td>
                    <td className="text-right">{b.discount_amount.toLocaleString('en-IN', {maximumFractionDigits: 2})}</td>
                  </tr>
                ))}
                {byBrand.length === 0 && (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                    {loading ? 'Loading…' : 'No scheme applications in this period.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Recent Applications</h3></div>
          <div className="card-body tight">
            <table className="data">
              <thead><tr>
                <th>When</th><th>Scheme</th><th>Party</th>
                <th className="text-right">Discount ₹</th>
              </tr></thead>
              <tbody>
                {schemeUsage.slice(0, 20).map((s, i) => (
                  <tr key={s.id || i}>
                    <td className="text-small">{s.applied_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td>{s.scheme_name || s.scheme_code}</td>
                    <td>{s.party_name}</td>
                    <td className="text-right">{(s.discount_amount || 0).toLocaleString('en-IN', {maximumFractionDigits: 2})}</td>
                  </tr>
                ))}
                {schemeUsage.length === 0 && (
                  <tr><td colSpan={4} style={{ textAlign: 'center', color: '#9ca3af', padding: 24 }}>
                    {loading ? 'Loading…' : 'No data yet.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
