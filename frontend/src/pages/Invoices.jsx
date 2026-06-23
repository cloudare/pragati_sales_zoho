import { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function Invoices() {
  const [list, setList] = useState([]);
  useEffect(() => { api.get('/api/invoices').then(r => setList(r.data)).catch(() => setList([])); }, []);

  return (
    <div>
      <div className="mb-md">
        <h2 className="mt-0 mb-0">Invoices</h2>
        <p className="text-muted text-small mb-0">PRD M5 · Zoho-side billing with scheme-adjusted prices</p>
      </div>
      <div className="card">
        <div className="card-body tight">
          <table className="data">
            <thead><tr>
              <th>Invoice #</th><th>Customer</th><th>Date</th>
              <th className="text-right">Total</th><th>Status</th>
            </tr></thead>
            <tbody>
              {list.map(i => (
                <tr key={i.invoice_id}>
                  <td className="text-mono">{i.invoice_number}</td>
                  <td>{i.customer_name}</td>
                  <td className="text-small">{i.date}</td>
                  <td className="text-right">₹{Number(i.total || 0).toFixed(2)}</td>
                  <td><span className={`pill pill-${i.status === 'paid' ? 'success' : 'info'}`}>
                    {i.status || '—'}
                  </span></td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr><td colSpan={5} className="text-center text-muted" style={{ padding: 32 }}>
                  No invoices yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
