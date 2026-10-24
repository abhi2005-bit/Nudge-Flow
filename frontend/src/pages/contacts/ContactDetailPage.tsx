import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Phone, Clock, Bot, Edit, Trash2, Calendar, Plus } from 'lucide-react';
import { contactsApi, followUpsApi, getApiError, type Contact } from '../../lib/api';
import { format, formatDistanceToNow, isPast } from 'date-fns';

export default function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editModal, setEditModal] = useState(false);
  const [deleteModal, setDeleteModal] = useState(false);
  const [editName, setEditName] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editError, setEditError] = useState('');

  const contactId = parseInt(id ?? '0');

  const { data: contact, isLoading, error } = useQuery({
    queryKey: ['contacts', contactId],
    queryFn: () => contactsApi.get(contactId),
    enabled: !!contactId,
  });

  const { data: followUps } = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => followUpsApi.list({ limit: 500 }),
  });

  const contactFollowUps = (followUps ?? []).filter((f) => f.contact_id === contactId);
  const pendingFUs = contactFollowUps.filter((f) => f.status === 'pending');
  const completedFUs = contactFollowUps.filter((f) => f.status === 'completed');

  const updateMut = useMutation({
    mutationFn: (data: { name: string; phone_number: string }) =>
      contactsApi.update(contactId, data),
    onSuccess: (updated) => {
      qc.setQueryData(['contacts', contactId], updated);
      qc.invalidateQueries({ queryKey: ['contacts'] });
      setEditModal(false);
    },
    onError: (e) => setEditError(getApiError(e)),
  });

  const deleteMut = useMutation({
    mutationFn: () => contactsApi.delete(contactId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] });
      navigate('/contacts', { replace: true });
    },
  });

  const openEdit = () => {
    setEditName(contact?.name ?? '');
    setEditPhone(contact?.phone_number ?? '');
    setEditError('');
    setEditModal(true);
  };

  if (isLoading) {
    return <div className="loading-overlay"><div className="spinner spinner-lg" /><span>Loading contact…</span></div>;
  }

  if (error || !contact) {
    return (
      <div style={{ padding: 'var(--space-6)' }}>
        <div className="alert alert-error">Contact not found.</div>
        <Link to="/contacts" className="btn btn-secondary" style={{ marginTop: '1rem' }}>
          <ArrowLeft size={14} /> Back to Contacts
        </Link>
      </div>
    );
  }

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
        <Link to="/contacts" className="btn btn-ghost btn-icon btn-sm">
          <ArrowLeft size={16} />
        </Link>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              background: 'var(--color-brand-100)', color: 'var(--color-brand-700)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 700, fontSize: '1rem', flexShrink: 0,
            }}>
              {contact.name.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>{contact.name}</h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-text-muted)', fontSize: '0.875rem', marginTop: 2 }}>
                <Phone size={13} />
                <span className="font-mono">{contact.phone_number}</span>
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button id="edit-contact-btn" className="btn btn-secondary btn-sm" onClick={openEdit}>
            <Edit size={14} /> Edit
          </button>
          <button
            id="delete-contact-btn"
            className="btn btn-ghost btn-sm"
            style={{ color: 'var(--color-error-600)' }}
            onClick={() => setDeleteModal(true)}
          >
            <Trash2 size={14} /> Delete
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Contact info card */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Contact Details</span>
          </div>
          <div className="card-body-sm">
            <div className="detail-row">
              <span className="detail-label">Name</span>
              <span className="detail-value">{contact.name}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Phone</span>
              <span className="detail-value font-mono">{contact.phone_number}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Added</span>
              <span className="detail-value">
                {format(new Date(contact.created_at), 'PPP')}
              </span>
            </div>
            <div className="detail-row" style={{ border: 'none' }}>
              <span className="detail-label">Follow-ups</span>
              <div className="detail-value" style={{ display: 'flex', gap: '0.5rem' }}>
                <span className="badge badge-yellow">{pendingFUs.length} pending</span>
                <span className="badge badge-green">{completedFUs.length} done</span>
              </div>
            </div>
          </div>
        </div>

        {/* Follow-ups */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Follow-ups ({contactFollowUps.length})</span>
            <Link to="/follow-ups" className="btn btn-primary btn-sm">
              <Plus size={14} /> Add Follow-up
            </Link>
          </div>
          {contactFollowUps.length === 0 ? (
            <div className="empty-state" style={{ padding: '2.5rem' }}>
              <div className="empty-state-icon"><Clock size={22} /></div>
              <div className="empty-state-title">No follow-ups</div>
              <div className="empty-state-desc">Add a follow-up to schedule your next touchpoint with {contact.name}.</div>
            </div>
          ) : (
            <div>
              {contactFollowUps
                .slice()
                .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime())
                .map((fu) => {
                  const overdue = fu.status === 'pending' && isPast(new Date(fu.due_at));
                  return (
                    <Link key={fu.id} to={`/follow-ups/${fu.id}`} style={{ textDecoration: 'none', display: 'block' }}>
                      <div
                        style={{
                          padding: '0.875rem 1.25rem',
                          borderBottom: '1px solid var(--color-gray-100)',
                          display: 'flex', alignItems: 'center', gap: '0.75rem',
                          transition: 'background var(--transition-fast)',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-gray-50)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 500, fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {fu.title}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: overdue ? 'var(--color-error-600)' : 'var(--color-text-muted)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Calendar size={11} />
                            {format(new Date(fu.due_at), 'PPP p')}
                            {overdue && ' · Overdue'}
                          </div>
                        </div>
                        <span className={`badge ${fu.status === 'completed' ? 'badge-green' : overdue ? 'badge-red' : 'badge-yellow'}`}>
                          {fu.status === 'completed' ? 'Done' : overdue ? 'Overdue' : 'Pending'}
                        </span>
                      </div>
                    </Link>
                  );
                })}
            </div>
          )}
        </div>
      </div>

      {/* Edit modal */}
      {editModal && (
        <div className="dialog-overlay" onClick={() => setEditModal(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Edit Contact</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditModal(false)}>✕</button>
            </div>
            <div className="dialog-body">
              {editError && <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{editError}</div>}
              <form onSubmit={(e) => { e.preventDefault(); updateMut.mutate({ name: editName, phone_number: editPhone }); }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label form-label-required">Name</label>
                    <input className="form-input" value={editName} onChange={(e) => setEditName(e.target.value)} required maxLength={150} />
                  </div>
                  <div className="form-group">
                    <label className="form-label form-label-required">Phone number</label>
                    <input className="form-input" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} required maxLength={30} />
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
              <span className="dialog-title">Delete Contact</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setDeleteModal(false)}>✕</button>
            </div>
            <div className="dialog-body">
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
                Are you sure you want to delete <strong>{contact.name}</strong>? All follow-ups will also be deleted. This cannot be undone.
              </p>
              <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0 }}>
                <button className="btn btn-secondary" onClick={() => setDeleteModal(false)}>Cancel</button>
                <button
                  className={`btn btn-danger${deleteMut.isPending ? ' btn-loading' : ''}`}
                  onClick={() => deleteMut.mutate()}
                  disabled={deleteMut.isPending}
                >
                  {deleteMut.isPending ? 'Deleting…' : 'Delete Contact'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
