import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Clock,
  Bot,
  Settings,
  MessageSquare,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/',          icon: <LayoutDashboard size={17} />, label: 'Dashboard', exact: true },
  { to: '/contacts',  icon: <Users size={17} />,           label: 'Contacts'  },
  { to: '/follow-ups',icon: <Clock size={17} />,           label: 'Follow-ups'},
  { to: '/agent',     icon: <Bot size={17} />,             label: 'Agent Console'},
  { to: '/settings',  icon: <Settings size={17} />,        label: 'Settings'  },
];

export default function AppShell() {
  const { logout, userEmail } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const initials = userEmail
    ? userEmail.slice(0, 2).toUpperCase()
    : 'NU';

  const displayEmail = userEmail ?? 'Signed in';

  return (
    <div className="app-shell">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="dialog-overlay"
          style={{ zIndex: 49 }}
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <nav className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        {/* Logo */}
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <MessageSquare size={18} color="white" />
          </div>
          <div>
            <div className="sidebar-logo-text">NudgeFlow AI</div>
            <div className="sidebar-logo-sub">WhatsApp CRM</div>
          </div>
        </div>

        {/* Navigation */}
        <div className="sidebar-section" style={{ flex: 1 }}>
          <div className="sidebar-section-label">Menu</div>
          {NAV_ITEMS.map(({ to, icon, label, exact }) => {
            const isActive = exact
              ? location.pathname === to
              : location.pathname.startsWith(to);
            return (
              <NavLink
                key={to}
                to={to}
                className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="nav-icon" style={{ display: 'flex' }}>{icon}</span>
                <span>{label}</span>
              </NavLink>
            );
          })}
        </div>

        {/* User footer */}
        <div className="sidebar-footer">
          <div className="sidebar-user" onClick={handleLogout} title="Sign out">
            <div className="sidebar-avatar">{initials}</div>
            <div className="sidebar-user-name">{displayEmail}</div>
            <LogOut size={15} style={{ color: 'var(--color-gray-500)', flexShrink: 0 }} />
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="main-content">
        {/* Mobile header */}
        <div
          className="page-header"
          style={{ display: 'none' }}
          id="mobile-header"
        >
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
            style={{ display: 'flex' }}
          >
            <Menu size={20} />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <MessageSquare size={18} color="var(--color-brand-600)" />
            <span style={{ fontWeight: 700, fontSize: '0.9375rem' }}>NudgeFlow AI</span>
          </div>
          <div style={{ width: 36 }} />
        </div>

        <div className="page-body" style={{ padding: 0 }}>
          <Outlet />
        </div>
      </main>

      <style>{`
        @media (max-width: 768px) {
          #mobile-header { display: flex !important; }
        }
      `}</style>
    </div>
  );
}
