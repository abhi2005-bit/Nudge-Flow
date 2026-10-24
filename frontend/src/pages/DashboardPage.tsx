import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Users, Clock, Bot, CheckCircle, AlertCircle, TrendingUp, Plus } from 'lucide-react';
import { contactsApi, followUpsApi, type Contact, type FollowUp } from '../lib/api';
import { formatDistanceToNow, isPast, isToday } from 'date-fns';

function StatCard({
  icon,
  iconBg,
  iconColor,
  label,
  value,
  loading,
  linkTo,
}: {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  label: string;
  value: number | string;
  loading?: boolean;
  linkTo?: string;
}) {
  const card = (
    <div className="stat-card" style={{ textDecoration: 'none' }}>
      <div className="stat-icon" style={{ background: iconBg, color: iconColor }}>
        {icon}
      </div>
      <div>
        <div className="stat-value" style={{ fontSize: '1.5rem' }}>
          {loading ? <span className="animate-pulse">—</span> : value}
        </div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
  return linkTo ? <Link to={linkTo} style={{ textDecoration: 'none', color: 'inherit' }}>{card}</Link> : card;
}

export default function DashboardPage() {
  const { data: contacts, isLoading: contactsLoading, error: contactsError } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 500 }),
  });

  const { data: followUps, isLoading: followUpsLoading, error: followUpsError } = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => followUpsApi.list({ limit: 500 }),
  });

  const pending = followUps?.filter((f) => f.status === 'pending') ?? [];
  const overdue = pending.filter((f) => isPast(new Date(f.due_at)));
  const dueToday = pending.filter((f) => isToday(new Date(f.due_at)));
  const completed = followUps?.filter((f) => f.status === 'completed') ?? [];

  const recentContacts = (contacts ?? []).slice(-5).reverse();
  const upcomingFollowUps = pending
    .slice()
    .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime())
    .slice(0, 5);

  const fetchError = contactsError || followUpsError;

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Your NudgeFlow AI overview</p>
      </div>

      {fetchError && (
        <div className="alert alert-error" style={{ marginBottom: 'var(--space-6)' }}>
          <AlertCircle size={16} style={{ flexShrink: 0 }} />
          <span>Failed to load dashboard data. Please check your backend connection.</span>
        </div>
      )}

      {/* Stats */}
      <div className="stat-grid" style={{ marginBottom: 'var(--space-6)' }}>
        <StatCard
          icon={<Users size={20} />}
          iconBg="var(--color-brand-50)"
          iconColor="var(--color-brand-600)"
          label="Total Contacts"
          value={contacts?.length ?? 0}
          loading={contactsLoading}
          linkTo="/contacts"
        />
        <StatCard
          icon={<Clock size={20} />}
          iconBg="var(--color-warning-50)"
          iconColor="var(--color-warning-600)"
          label="Pending Follow-ups"
          value={pending.length}
          loading={followUpsLoading}
          linkTo="/follow-ups"
        />
        <StatCard
          icon={<AlertCircle size={20} />}
          iconBg="var(--color-error-50)"
          iconColor="var(--color-error-600)"
          label="Overdue"
          value={overdue.length}
          loading={followUpsLoading}
          linkTo="/follow-ups"
        />
        <StatCard
          icon={<CheckCircle size={20} />}
          iconBg="var(--color-success-50)"
          iconColor="var(--color-success-600)"
          label="Completed"
          value={completed.length}
          loading={followUpsLoading}
          linkTo="/follow-ups"
        />
      </div>

      {/* Content grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
        {/* Upcoming follow-ups */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Upcoming Follow-ups</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
                {dueToday.length > 0 ? `${dueToday.length} due today` : 'Next scheduled'}
              </div>
            </div>
            <Link to="/follow-ups" className="btn btn-secondary btn-sm">View all</Link>
          </div>
          <div>
            {followUpsLoading ? (
              <div className="loading-overlay" style={{ padding: '2rem' }}>
                <div className="spinner" />
              </div>
            ) : upcomingFollowUps.length === 0 ? (
              <div className="empty-state" style={{ padding: '2rem' }}>
                <div className="empty-state-icon"><Clock size={22} /></div>
                <div className="empty-state-title">No pending follow-ups</div>
                <Link to="/follow-ups" className="btn btn-primary btn-sm">
                  <Plus size={14} /> Add follow-up
                </Link>
              </div>
            ) : (
              <div>
                {upcomingFollowUps.map((fu) => {
                  const isOverdue = isPast(new Date(fu.due_at));
                  return (
                    <Link
                      key={fu.id}
                      to={`/follow-ups/${fu.id}`}
                      style={{ textDecoration: 'none', display: 'block' }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.75rem',
                          padding: '0.75rem 1.25rem',
                          borderBottom: '1px solid var(--color-gray-100)',
                          transition: 'background var(--transition-fast)',
                          cursor: 'pointer',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-gray-50)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                      >
                        <div
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            background: isOverdue ? 'var(--color-error-500)' : 'var(--color-warning-500)',
                            flexShrink: 0,
                          }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 500, fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {fu.title}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: isOverdue ? 'var(--color-error-600)' : 'var(--color-text-muted)', marginTop: 2 }}>
                            {isOverdue
                              ? `Overdue — ${formatDistanceToNow(new Date(fu.due_at), { addSuffix: true })}`
                              : formatDistanceToNow(new Date(fu.due_at), { addSuffix: true })}
                          </div>
                        </div>
                        <span className={`badge ${isOverdue ? 'badge-red' : 'badge-yellow'}`}>
                          {isOverdue ? 'Overdue' : 'Pending'}
                        </span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Recent contacts */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Recent Contacts</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
                Latest additions
              </div>
            </div>
            <Link to="/contacts" className="btn btn-secondary btn-sm">View all</Link>
          </div>
          <div>
            {contactsLoading ? (
              <div className="loading-overlay" style={{ padding: '2rem' }}>
                <div className="spinner" />
              </div>
            ) : recentContacts.length === 0 ? (
              <div className="empty-state" style={{ padding: '2rem' }}>
                <div className="empty-state-icon"><Users size={22} /></div>
                <div className="empty-state-title">No contacts yet</div>
                <Link to="/contacts" className="btn btn-primary btn-sm">
                  <Plus size={14} /> Add contact
                </Link>
              </div>
            ) : (
              <div>
                {recentContacts.map((c) => (
                  <Link
                    key={c.id}
                    to={`/contacts/${c.id}`}
                    style={{ textDecoration: 'none', display: 'block' }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.75rem',
                        padding: '0.75rem 1.25rem',
                        borderBottom: '1px solid var(--color-gray-100)',
                        transition: 'background var(--transition-fast)',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-gray-50)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                    >
                      <div
                        style={{
                          width: 32, height: 32, borderRadius: '50%',
                          background: 'var(--color-brand-100)',
                          color: 'var(--color-brand-700)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontWeight: 700, fontSize: '0.75rem', flexShrink: 0,
                        }}
                      >
                        {c.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 500, fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {c.name}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
                          {c.phone_number}
                        </div>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div
        className="card"
        style={{ marginTop: 'var(--space-6)', display: 'flex', alignItems: 'center', gap: 'var(--space-4)', padding: 'var(--space-5) var(--space-6)', flexWrap: 'wrap' }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          <div className="card-title" style={{ fontSize: '0.9375rem' }}>Quick actions</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
            Jump to common tasks
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <Link to="/contacts" className="btn btn-secondary btn-sm">
            <Users size={14} /> New Contact
          </Link>
          <Link to="/follow-ups" className="btn btn-secondary btn-sm">
            <Clock size={14} /> New Follow-up
          </Link>
          <Link to="/agent" className="btn btn-primary btn-sm">
            <Bot size={14} /> Run Agent
          </Link>
        </div>
      </div>
    </div>
  );
}
