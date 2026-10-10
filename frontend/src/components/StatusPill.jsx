const STYLES = {
  active: { fg: '#0e4f4a', bg: '#e4f0ee' },
  screened: { fg: '#5b6570', bg: '#eceeec' },
  evaluated: { fg: '#2f6fe0', bg: '#eaf1fd' },
  advanced: { fg: '#1e8f5f', bg: '#e9f6ef' },
  rejected: { fg: '#d64545', bg: '#fceaea' },
  closed: { fg: '#5b6570', bg: '#eceeec' },
};

export default function StatusPill({ status }) {
  const style = STYLES[status] || STYLES.screened;
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium capitalize"
      style={{ color: style.fg, backgroundColor: style.bg }}
    >
      {status || 'unknown'}
    </span>
  );
}
