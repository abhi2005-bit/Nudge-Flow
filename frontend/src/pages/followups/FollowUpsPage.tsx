import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Clock, Plus, Search, Calendar, CheckCircle, Trash2, Edit, Bot } from 'lucide-react';
import { followUpsApi, contactsApi, getApiError, type FollowUp } from '../../lib/api';
import { format, formatDistanceToNow, isPast } from 'date-fns';

function FollowUpStatusBadge({ fu }: { fu: FollowUp }) {
  if (fu.status === 'completed') return <span className="badge badge-green">Completed</span>;
  if (isPast(new Date(fu.due_at))) return <span className="badge badge-red">Overdue</span>;
  return <span className="badge badge-yellow">Pending</span>;
}

export default function FollowUpsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('all');
  const [modal, setModal] = useState<'create' | 'edit' | 'delete' | null>(null);
  const [selected, setSelected] = useState<FollowUp | null>(null);
  const [mutError, setMutError] = useState('');

  // Form state
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [contactId, setContactId] = useState('');
  const [dueAt, setDueAt] = useState('');

  const { data: followUps, isLoading, error: fuError } = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => followUpsApi.list({ limit: 500 }),
  });

  const { data: contacts } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 500 }),
  });

  const createMut = useMutation({
    mutationFn: () => {
      if (!contactId || isNaN(parseInt(contactId))) {
        throw new Error('Please select a contact.');
      }
      if (!title.trim()) {
        throw new Error('Please provide a title.');
      }
      if (!dueAt) {
        throw new Error('Please select a due date.');
      }
      const due = new Date(dueAt);
      if (isNaN(due.getTime())) {
        throw new Error('Invalid due date.');
      }
      return followUpsApi.create({
        contact_id: parseInt(contactId),
        title: title.trim(),
        notes: notes.trim() || undefined,
        due_at: due.toISOString(),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['follow-ups'] });
      setModal(null);
      resetForm();
    },
    onError: (e) => setMutError(getApiError(e)),
  });

  const completeMut = useMutation({
    mutationFn: (id: number) => followUpsApi.update(id, { status: 'completed' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['follow-ups'] }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => followUpsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['follow-ups'] }); setModal(null); },
  });

function getFutureDateTimeLocal(daysAhead: number, hour: number = 10): string {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  d.setHours(hour, 0, 0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

  const resetForm = () => {
    setTitle('');
    setNotes('');
    setContactId('');
    setDueAt(getFutureDateTimeLocal(1, 10));
  };

  const openCreate = () => { resetForm(); setMutError(''); setModal('create'); };

  const contactMap = new Map((contacts ?? []).map((c) => [c.id, c]));

  const filtered = (followUps ?? [])
    .filter((f) => {
      if (filter === 'pending') return f.status === 'pending';
      if (filter === 'completed') return f.status === 'completed';
      return true;
    })
    .filter((f) => {
      const contact = contactMap.get(f.contact_id);
      return (
        f.title.toLowerCase().includes(search.toLowerCase()) ||
        contact?.name.toLowerCase().includes(search.toLowerCase())
      );
    })
    .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime());

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-title">Follow-ups</h1>
          <p className="page-subtitle">Track and schedule customer outreach</p>
        </div>
        <button id="add-followup-btn" className="btn btn-primary" onClick={openCreate}>
          <Plus size={16} /> Add Follow-up
        </button>
      </div>

      {fuError && (
        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
          Failed to load follow-ups: {getApiError(fuError)}
        </div>
      )}

      {/* Filters & search */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="search-bar" style={{ maxWidth: 350 }}>
          <Search size={15} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
          <input
            id="followups-search"
            placeholder="Search follow-ups or contacts…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {(['all', 'pending', 'completed'] as const).map((f) => (
            <button
              key={f}
              className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="loading-overlay"><div className="spinner spinner-lg" /><span>Loading follow-ups…</span></div>
      ) : fuError ? null : filtered.length === 0 ? (
        <div className="card">
          <div className="empty-state" style={{ padding: '4rem' }}>
            <div className="empty-state-icon"><Clock size={26} /></div>
            <div className="empty-state-title">
              {search || filter !== 'all' ? 'No follow-ups match your filters' : 'No follow-ups yet'}
            </div>
            <div className="empty-state-desc">
              {!search && filter === 'all' && 'Schedule your first customer follow-up.'}
            </div>
            {!search && filter === 'all' && (
              <button className="btn btn-primary" onClick={openCreate}>
                <Plus size={14} /> Add Follow-up
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Contact</th>
                <th>Due</th>
                <th>Status</th>
                <th style={{ width: 120 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((fu) => {
                const contact = contactMap.get(fu.contact_id);
                return (
                  <tr key={fu.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/follow-ups/${fu.id}`)}>
                    <td style={{ fontWeight: 500 }}>{fu.title}</td>
                    <td>
                      {contact ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <div style={{
                            width: 24, height: 24, borderRadius: '50%',
                            background: 'var(--color-brand-100)', color: 'var(--color-brand-700)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontWeight: 700, fontSize: '0.6875rem', flexShrink: 0,
                          }}>
                            {contact.name.slice(0, 2).toUpperCase()}
                          </div>
                          <span>{contact.name}</span>
                        </div>
                      ) : <span style={{ color: 'var(--color-text-muted)' }}>Unknown</span>}
                    </td>
                    <td style={{ color: fu.status === 'pending' && isPast(new Date(fu.due_at)) ? 'var(--color-error-600)' : 'var(--color-text-secondary)', fontSize: '0.8125rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Calendar size={12} />
                        {format(new Date(fu.due_at), 'MMM d, yyyy')}
                      </div>
                      <div style={{ fontSize: '0.75rem', marginTop: 2 }}>
                        {formatDistanceToNow(new Date(fu.due_at), { addSuffix: true })}
                      </div>
                    </td>
                    <td><FollowUpStatusBadge fu={fu} /></td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: '0.25rem' }}>
                        {fu.status === 'pending' && (
                          <button
                            id={`complete-fu-${fu.id}`}
                            className="btn btn-ghost btn-icon btn-sm"
                            data-tooltip="Mark complete"
                            style={{ color: 'var(--color-success-600)' }}
                            onClick={() => completeMut.mutate(fu.id)}
                          ><CheckCircle size={14} /></button>
                        )}
                        <Link
                          to={`/agent?follow_up_id=${fu.id}`}
                          className="btn btn-ghost btn-icon btn-sm"
                          data-tooltip="Run Agent"
                          style={{ color: 'var(--color-brand-600)' }}
                          onClick={(e) => e.stopPropagation()}
                        ><Bot size={14} /></Link>
                        <button
                          id={`delete-fu-${fu.id}`}
                          className="btn btn-ghost btn-icon btn-sm"
                          data-tooltip="Delete"
                          style={{ color: 'var(--color-error-500)' }}
                          onClick={() => { setSelected(fu); setMutError(''); setModal('delete'); }}
                        ><Trash2 size={14} /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create modal */}
      {modal === 'create' && (
        <div className="dialog-overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="dialog-header">
              <span className="dialog-title">Add Follow-up</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setModal(null)}>✕</button>
            </div>
            <div className="dialog-body">
              {mutError && <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{mutError}</div>}
              <form onSubmit={(e) => { e.preventDefault(); createMut.mutate(); }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label form-label-required">Contact</label>
                    <select
                      id="fu-contact"
                      className="form-select"
                      value={contactId}
                      onChange={(e) => setContactId(e.target.value)}
                      required
                    >
                      <option value="">Select a contact…</option>
                      {(contacts ?? []).map((c) => (
                        <option key={c.id} value={c.id}>{c.name} ({c.phone_number})</option>
                      ))}
                    </select>
                    {contacts?.length === 0 && (
                      <span className="form-hint">No contacts yet — <Link to="/contacts">add one first</Link></span>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label form-label-required">Title</label>
                    <input
                      id="fu-title"
                      className="form-input"
                      placeholder="e.g. Check in on project status"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      required
                      maxLength={200}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Notes</label>
                    <textarea
                      id="fu-notes"
                      className="form-textarea"
                      placeholder="Optional context or reminders…"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="form-group">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <label className="form-label form-label-required" htmlFor="fu-due" style={{ marginBottom: 0 }}>Due date & time</label>
                      <div style={{ display: 'flex', gap: '0.25rem' }}>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: '0.75rem', padding: '0.125rem 0.375rem', height: 'auto' }}
                          onClick={() => setDueAt(getFutureDateTimeLocal(1, 10))}
                        >
                          Tomorrow
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: '0.75rem', padding: '0.125rem 0.375rem', height: 'auto' }}
                          onClick={() => setDueAt(getFutureDateTimeLocal(3, 10))}
                        >
                          +3 Days
                        </button>
                      </div>
                    </div>
                    <input
                      id="fu-due"
                      type="datetime-local"
                      className="form-input"
                      value={dueAt}
                      onChange={(e) => setDueAt(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0, marginTop: '1.5rem' }}>
                  <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                  <button
                    id="create-fu-submit"
                    type="submit"
                    className={`btn btn-primary${createMut.isPending ? ' btn-loading' : ''}`}
                    disabled={createMut.isPending}
                  >
                    {createMut.isPending ? 'Adding…' : 'Add Follow-up'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Delete modal */}
      {modal === 'delete' && selected && (
        <div className="dialog-overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Delete Follow-up</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setModal(null)}>✕</button>
            </div>
            <div className="dialog-body">
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
                Delete <strong>"{selected.title}"</strong>? This cannot be undone.
              </p>
              <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0 }}>
                <button className="btn btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                <button
                  className={`btn btn-danger${deleteMut.isPending ? ' btn-loading' : ''}`}
                  onClick={() => deleteMut.mutate(selected.id)}
                  disabled={deleteMut.isPending}
                >
                  {deleteMut.isPending ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
