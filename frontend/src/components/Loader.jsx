export default function Loader({ label = 'Loading…', size = 48 }) {
  return (
    <div className="loader-wrap">
      <img src="/loader.gif" alt="" width={size} height={size} className="loader-gif" />
      {label && <div className="loader-label">{label}</div>}
    </div>
  );
}