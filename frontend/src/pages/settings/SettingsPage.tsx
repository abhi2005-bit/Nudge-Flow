import React from 'react';
import { Settings, Shield, Zap, MessageSquare, AlertCircle, Info, Database, Key } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

export default function SettingsPage() {
  const { userEmail } = useAuth();

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Manage your account and integration configuration</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Account info */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Shield size={16} style={{ color: 'var(--color-brand-600)' }} />
              <span className="card-title">Account</span>
            </div>
          </div>
          <div className="card-body-sm">
            <div className="detail-row">
              <span className="detail-label">Email</span>
              <span className="detail-value">{userEmail ?? '—'}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Role</span>
              <span className="detail-value"><span className="badge badge-blue">Owner</span></span>
            </div>
            <div className="detail-row" style={{ border: 'none' }}>
              <span className="detail-label">Auth</span>
              <span className="detail-value">
                <span className="badge badge-green">JWT Bearer</span>
              </span>
            </div>
          </div>
        </div>

        {/* Integration status */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Zap size={16} style={{ color: 'var(--color-warning-600)' }} />
              <span className="card-title">Integrations</span>
            </div>
          </div>
          <div className="card-body-sm">
            {[
              {
                icon: <MessageSquare size={15} />,
                name: 'WhatsApp (mock)',
                status: 'active',
                note: 'Mock tool — no real messages sent',
              },
              {
                icon: <Database size={15} />,
                name: 'Database',
                status: 'active',
                note: 'PostgreSQL via SQLAlchemy',
              },
              {
                icon: <Key size={15} />,
                name: 'LLM API',
                status: 'optional',
                note: 'Set NUDGEFLOW_LLM_API_KEY for AI drafts',
              },
            ].map(({ icon, name, status, note }) => (
              <div key={name} className="detail-row" style={{ gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 160 }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>{icon}</span>
                  <span className="detail-label" style={{ minWidth: 'auto' }}>{name}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
                  <span className={`badge ${status === 'active' ? 'badge-green' : 'badge-gray'}`} style={{ alignSelf: 'flex-start' }}>
                    {status}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{note}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Security */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Shield size={16} style={{ color: 'var(--color-success-600)' }} />
              <span className="card-title">Security</span>
            </div>
          </div>
          <div className="card-body-sm">
            {[
              { label: 'Token type', value: 'JWT Bearer (RS256 / HS256)' },
              { label: 'Token expiry', value: '30 minutes (configurable)' },
              { label: 'Tenant isolation', value: 'All data is scoped per tenant' },
              { label: 'Credentials', value: 'Never exposed to frontend' },
            ].map(({ label, value }) => (
              <div key={label} className="detail-row">
                <span className="detail-label">{label}</span>
                <span className="detail-value">{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Important notices */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="alert alert-warning">
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Mock messaging only</div>
              <div style={{ fontSize: '0.8125rem' }}>
                The current WhatsApp integration is a mock tool. No real messages are sent. Agent-run approvals do not contact any external system.
              </div>
            </div>
          </div>

          <div className="alert alert-info">
            <Info size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>LLM configuration</div>
              <div style={{ fontSize: '0.8125rem' }}>
                To enable AI-generated message drafts, set <code style={{ background: 'rgba(0,0,0,0.06)', padding: '0 3px', borderRadius: 3 }}>NUDGEFLOW_LLM_API_KEY</code> and <code style={{ background: 'rgba(0,0,0,0.06)', padding: '0 3px', borderRadius: 3 }}>NUDGEFLOW_LLM_MODEL</code> in the backend <code>.env</code> file. Without these, a deterministic template is used.
              </div>
            </div>
          </div>

          <div className="alert alert-info">
            <Info size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Backend configuration</div>
              <div style={{ fontSize: '0.8125rem' }}>
                API base URL: <code style={{ background: 'rgba(0,0,0,0.06)', padding: '0 3px', borderRadius: 3 }}>{import.meta.env.VITE_API_BASE_URL}</code>.
                To change, update <code style={{ background: 'rgba(0,0,0,0.06)', padding: '0 3px', borderRadius: 3 }}>VITE_API_BASE_URL</code> in the frontend <code>.env</code> file.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Agent run states reference */}
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Settings size={16} style={{ color: 'var(--color-gray-500)' }} />
            <span className="card-title">Agent Run States Reference</span>
          </div>
        </div>
        <div className="card-body-sm">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
            {[
              { status: 'awaiting_approval', label: 'Awaiting Approval', desc: 'Draft is ready. Human approval required before execution.' },
              { status: 'rejected', label: 'Rejected', desc: 'The proposed message was rejected. Run is terminal.' },
              { status: 'executing', label: 'Executing', desc: 'The mock messaging tool is running.' },
              { status: 'completed', label: 'Completed', desc: 'Message executed successfully (mock).' },
              { status: 'failed', label: 'Failed', desc: 'Execution failed. Recovery may be possible.' },
              { status: 'ready_to_execute', label: 'Ready to Execute', desc: 'Recovered from a failed/interrupted state. Ready for re-execution.' },
              { status: 'outcome_uncertain', label: 'Outcome Uncertain', desc: 'Execution ran but outcome could not be confirmed. Manual verification required.' },
            ].map(({ status, label, desc }) => (
              <div key={status} className={`run-status-bar ${status}`} style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.25rem' }}>
                <div style={{ fontWeight: 600 }}>{label}</div>
                <div style={{ fontSize: '0.8125rem', opacity: 0.85 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
