import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Calendar, Clock, Edit, Trash2, CheckCircle, Bot, User, StickyNote } from 'lucide-react';
import { followUpsApi, contactsApi, getApiError, type FollowUp } from '../../lib/api';
import { format, formatDistanceToNow, isPast } from 'date-fns';

export default function FollowUpDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const fuId = parseInt(id ?? '0');

  const [editModal, setEditModal] = useState(false);
  const [deleteModal, setDeleteModal] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [editDue, setEditDue] = useState('');
  const [editError, setEditError] = useState('');

  const { data: fu, isLoading, error } = useQuery({
    queryKey: ['follow-ups', fuId],
    queryFn: () => followUpsApi.get(fuId),
    enabled: !!fuId,
  });

  const { data: contacts } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 500 }),
  });

  const contact = contacts?.find((c) => c.id === fu?.contact_id);

  const updateMut = useMutation({
    mutationFn: (data: Parameters<typeof followUpsApi.update>[1]) =>
      followUpsApi.update(fuId, data),
    onSuccess: (updated) => {
      qc.setQueryData(['follow-ups', fuId], updated);
      qc.invalidateQueries({ queryKey: ['follow-ups'] });
      setEditModal(false);
    },
    onError: (e) => setEditError(getApiError(e)),
  });

  const completeMut = useMutation({
    mutationFn: () => followUpsApi.update(fuId, { status: 'completed' }),
    onSuccess: (updated) => {
      qc.setQueryData(['follow-ups', fuId], updated);
      qc.invalidateQueries({ queryKey: ['follow-ups'] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => followUpsApi.delete(fuId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['follow-ups'] });
      navigate('/follow-ups', { replace: true });
    },
  });

  const openEdit = () => {
    if (!fu) return;
    setEditTitle(fu.title);
    setEditNotes(fu.notes ?? '');
    // Convert to datetime-local format
    const d = new Date(fu.due_at);
    setEditDue(new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16));
    setEditError('');
    setEditModal(true);
  };

  if (isLoading) {
    return <div className="loading-overlay"><div className="spinner spinner-lg" /><span>Loading…</span></div>;
  }

  if (error || !fu) {
    return (
      <div style={{ padding: 'var(--space-6)' }}>
        <div className="alert alert-error">Follow-up not found.</div>
        <Link to="/follow-ups" className="btn btn-secondary" style={{ marginTop: '1rem' }}>
          <ArrowLeft size={14} /> Back
        </Link>
      </div>
    );
  }

  const overdue = fu.status === 'pending' && isPast(new Date(fu.due_at));

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1.5rem' }}>
        <Link to="/follow-ups" className="btn btn-ghost btn-icon btn-sm" style={{ marginTop: 4 }}>
          <ArrowLeft size={16} />
        </Link>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.375rem' }}>{fu.title}</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            {fu.status === 'completed'
              ? <span className="badge badge-green"><CheckCircle size={11} /> Completed</span>
              : overdue
              ? <span className="badge badge-red"><Clock size={11} /> Overdue</span>
              : <span className="badge badge-yellow"><Clock size={11} /> Pending</span>}
            <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
              Due {format(new Date(fu.due_at), 'PPPp')}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
          {fu.status === 'pending' && (
            <button
              id="mark-complete-btn"
              className={`btn btn-success btn-sm${completeMut.isPending ? ' btn-loading' : ''}`}
              onClick={() => completeMut.mutate()}
              disabled={completeMut.isPending}
            >
              <CheckCircle size={14} /> Mark Complete
            </button>
          )}
          <button id="edit-fu-btn" className="btn btn-secondary btn-sm" onClick={openEdit}>
            <Edit size={14} /> Edit
          </button>
          <Link to={`/agent?follow_up_id=${fu.id}`} className="btn btn-primary btn-sm">
            <Bot size={14} /> Run Agent
          </Link>
          <button
            id="delete-fu-btn"
            className="btn btn-ghost btn-sm"
            style={{ color: 'var(--color-error-600)' }}
            onClick={() => setDeleteModal(true)}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Details */}
        <div className="card">
          <div className="card-header"><span className="card-title">Details</span></div>
          <div className="card-body-sm">
            <div className="detail-row">
              <span className="detail-label"><User size={13} style={{ display: 'inline', marginRight: 4 }} />Contact</span>
              <div className="detail-value">
                {contact ? (
                  <Link to={`/contacts/${contact.id}`} style={{ color: 'var(--color-brand-600)', fontWeight: 500 }}>
                    {contact.name}
                  </Link>
                ) : <span className="text-muted">Unknown (ID: {fu.contact_id})</span>}
              </div>
            </div>
            <div className="detail-row">
              <span className="detail-label"><Calendar size={13} style={{ display: 'inline', marginRight: 4 }} />Due date</span>
              <div className="detail-value">
                <div>{format(new Date(fu.due_at), 'PPPp')}</div>
                <div style={{ fontSize: '0.75rem', color: overdue ? 'var(--color-error-600)' : 'var(--color-text-muted)', marginTop: 2 }}>
                  {formatDistanceToNow(new Date(fu.due_at), { addSuffix: true })}
                </div>
              </div>
            </div>
            <div className="detail-row">
              <span className="detail-label">Status</span>
              <span className="detail-value">
                {fu.status === 'completed'
                  ? <span className="badge badge-green">Completed</span>
                  : overdue
                  ? <span className="badge badge-red">Overdue</span>
                  : <span className="badge badge-yellow">Pending</span>}
              </span>
            </div>
            <div className="detail-row" style={{ border: 'none' }}>
              <span className="detail-label">Created</span>
              <span className="detail-value" style={{ color: 'var(--color-text-secondary)' }}>
                {format(new Date(fu.created_at), 'PPP')}
              </span>
            </div>
          </div>
        </div>

        {/* Notes */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><StickyNote size={15} style={{ display: 'inline', marginRight: 6 }} />Notes</span>
          </div>
          <div className="card-body">
            {fu.notes ? (
              <div style={{
                background: 'var(--color-gray-50)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: '0.875rem 1rem',
                fontSize: '0.875rem',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
              }}>
                {fu.notes}
              </div>
            ) : (
              <div style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', fontStyle: 'italic' }}>
                No notes added yet. Click Edit to add context or reminders.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Agent CTA */}
      {fu.status === 'pending' && (
        <div
          className="card"
          style={{ marginTop: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.25rem 1.5rem', flexWrap: 'wrap', background: 'linear-gradient(135deg, var(--color-brand-50) 0%, var(--color-purple-50) 100%)', borderColor: 'var(--color-brand-200)' }}
        >
          <div style={{ width: 40, height: 40, borderRadius: 'var(--radius-md)', background: 'var(--color-brand-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Bot size={20} color="white" />
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--color-brand-900)' }}>
              Let NudgeFlow AI draft a message
            </div>
            <div style={{ fontSize: '0.8125rem', color: 'var(--color-brand-700)', marginTop: 2 }}>
              The agent will analyze the follow-up context and propose a WhatsApp message for your review. You approve before anything is sent.
            </div>
          </div>
          <Link to={`/agent?follow_up_id=${fu.id}`} className="btn btn-primary">
            <Bot size={15} /> Run Agent
          </Link>
        </div>
      )}

      {/* Edit modal */}
      {editModal && (
        <div className="dialog-overlay" onClick={() => setEditModal(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Edit Follow-up</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditModal(false)}>✕</button>
            </div>
            <div className="dialog-body">
              {editError && <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{editError}</div>}
              <form onSubmit={(e) => {
                e.preventDefault();
                updateMut.mutate({
                  title: editTitle,
                  notes: editNotes || undefined,
                  due_at: new Date(editDue).toISOString(),
                });
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label form-label-required">Title</label>
                    <input className="form-input" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} required maxLength={200} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Notes</label>
                    <textarea className="form-textarea" value={editNotes} onChange={(e) => setEditNotes(e.target.value)} rows={3} />
                  </div>
                  <div className="form-group">
                    <label className="form-label form-label-required">Due date & time</label>
                    <input type="datetime-local" className="form-input" value={editDue} onChange={(e) => setEditDue(e.target.value)} required />
                  </div>
                </div>
                <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0, marginTop: '1.5rem' }}>
                  <button type="button" className="btn btn-secondary" onClick={() => setEditModal(false)}>Cancel</button>
                  <button type="submit" className={`btn btn-primary${updateMut.isPending ? ' btn-loading' : ''}`} disabled={updateMut.isPending}>
                    {updateMut.isPending ? 'Saving…' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Delete modal */}
      {deleteModal && (
        <div className="dialog-overlay" onClick={() => setDeleteModal(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Delete Follow-up</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setDeleteModal(false)}>✕</button>
            </div>
            <div className="dialog-body">
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
                Delete "<strong>{fu.title}</strong>"? This cannot be undone.
              </p>
              <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0 }}>
                <button className="btn btn-secondary" onClick={() => setDeleteModal(false)}>Cancel</button>
                <button
                  className={`btn btn-danger${deleteMut.isPending ? ' btn-loading' : ''}`}
                  onClick={() => deleteMut.mutate()}
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
