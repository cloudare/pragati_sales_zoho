import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';

/**
 * Typeahead for Zoho contact cache (vendor/customer pickers).
 *
 * Usage:
 *   <ContactPicker
 *     type="vendor"
 *     value={vendorName}
 *     onSelect={(c) => { setVendor(c.name); setVendorZohoId(c.zoho_contact_id); }}
 *   />
 */
export function ContactPicker({ type = "vendor", value = "", onSelect, placeholder, required }) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => { setQuery(value); }, [value]);

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const search = (q) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (!q || q.length < 2) { setResults([]); return; }
      setLoading(true);
      try {
        const r = await api.get('/api/sync/zoho/contacts',
          { params: { q, contact_type: type, limit: 10 } });
        setResults(r.data);
      } catch { setResults([]); }
      setLoading(false);
    }, 200);
  };

  const pick = (c) => {
    setQuery(c.name);
    setOpen(false);
    onSelect && onSelect(c);
  };

  return (
    <div className="typeahead" ref={containerRef}>
      <input
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); search(e.target.value); }}
        onFocus={() => { setOpen(true); if (query.length >= 2) search(query); }}
        placeholder={placeholder || `Search ${type}…`}
        required={required}
        autoComplete="off"
      />
      {open && (results.length > 0 || loading) && (
        <div className="typeahead-results">
          {loading && <div className="typeahead-result text-muted">Searching…</div>}
          {!loading && results.map(c => (
            <div key={c.zoho_contact_id} className="typeahead-result" onClick={() => pick(c)}>
              <div>{c.name}</div>
              <span className="meta">
                {c.party_group && `${c.party_group} · `}
                {c.gst_no || c.phone || c.zoho_contact_id}
              </span>
            </div>
          ))}
          {!loading && results.length === 0 && query.length >= 2 && (
            <div className="typeahead-result text-muted">
              No matches — type a free-text name, or run a master sync.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
