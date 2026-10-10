import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function AppShell({ children }) {
  const { company, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex flex-col bg-paper">
      {/* Top navbar */}
      <header 
        className="shrink-0 px-8 py-4 flex items-center justify-between" 
        style={{ backgroundColor: 'var(--color-rail-dark)' }}
      >
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-md bg-white flex items-center justify-center p-1 shrink-0">
            <img src="/brand/aurax-mark.png" alt="" className="w-full h-full object-contain" />
          </div>
          <span className="font-display font-semibold text-white text-lg tracking-tight">AuraX-AI</span>
          
          <nav className="ml-8 flex items-center gap-4">
            <NavLink
              to="/dashboard"
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'
                }`
              }
            >
              Jobs
            </NavLink>
            <NavLink
              to="/pipeline"
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'
                }`
              }
            >
              Pipeline
            </NavLink>
            <NavLink
              to="/analytics"
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'
                }`
              }
            >
              Analytics
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'
                }`
              }
            >
              Settings
            </NavLink>
          </nav>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wide text-white/40 font-medium">Signed in as</p>
            <p className="text-sm text-white font-medium truncate">{company?.company_name || 'Company'}</p>
          </div>
          <button
            onClick={handleLogout}
            className="text-xs font-medium text-white/50 hover:text-white transition-colors border border-white/20 px-3 py-1.5 rounded-md hover:border-white/40"
          >
            Log out
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
