import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';

/**
 * Typeahead - lookup from a ZohoContactCache or ZohoItemCache search endpoint.
 *
 * Props:
 *   value, onChange(value)          - the display name (string)
 *   onSelect({id, name, ...})        - called when an option is picked
 *   endpoint                         - one of '/api/sync/zoho/contacts', '/api/sync/zoho/items'
 *   extraParams                      - additional query params (e.g. {contact_type: 'vendor'})
 *   placeholder                      - input placeholder
 *   idField                          - which field is the ID ('zoho_contact_id' or 'zoho_item_id')
 */
export default function Typeahead({
  value, onChange, onSelect, endpoint, extraParams = {},
  placeholder = 'Type to search...', idField = 'zoho_contact_id',
}) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const timer = useRef(null);

  const search = async (q) => {
    if (!q || q.length < 2) { setResults([]); return; }
    try {
      const r = await api.get(endpoint, { params: { q, ...extraParams, limit: 8 } });
      setResults(r.data || []);
    } catch { setResults([]); }
  };

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => search(value), 250);
    return () => clearTimeout(timer.current);
  }, [value]);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const pick = (r) => {
    onChange(r.name);
    onSelect && onSelect(r);
    setOpen(false);
  };

  return (
    <div className="typeahead" ref={wrapRef}>
      <input value={value} onChange={e => { onChange(e.target.value); setOpen(true); }}
             onFocus={() => setOpen(true)} placeholder={placeholder} autoComplete="off" />
      {open && results.length > 0 && (
        <div className="typeahead-results">
          {results.map(r => (
            <div key={r[idField]} className="typeahead-result" onClick={() => pick(r)}>
              <div><strong>{r.name}</strong></div>
              <span className="meta">
                {r.party_group && `${r.party_group} · `}
                {r.gst_no && `${r.gst_no} · `}
                {r.brand && `${r.brand} · `}
                {r.sku && `SKU: ${r.sku}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
