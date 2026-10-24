import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Users, Plus, Search, Phone, Trash2, Edit, ChevronRight } from 'lucide-react';
import { contactsApi, getApiError, type Contact } from '../../lib/api';
import { formatDistanceToNow } from 'date-fns';

interface ContactFormProps {
  initial?: Partial<Contact>;
  onSubmit: (data: { name: string; phone_number: string }) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  error?: string;
  submitLabel?: string;
}

function ContactForm({ initial, onSubmit, onCancel, loading, error, submitLabel = 'Save' }: ContactFormProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [phone, setPhone] = useState(initial?.phone_number ?? '');
  const [formError, setFormError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    try {
      await onSubmit({ name, phone_number: phone });
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Failed to save contact.');
    }
  };

  const displayError = formError || error;

  return (
    <form onSubmit={handleSubmit}>
      {displayError && (
        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{displayError}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div className="form-group">
          <label className="form-label form-label-required" htmlFor="contact-name">Name</label>
          <input
            id="contact-name"
            className="form-input"
            placeholder="Jane Smith"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={150}
          />
        </div>
        <div className="form-group">
          <label className="form-label form-label-required" htmlFor="contact-phone">Phone number</label>
          <input
            id="contact-phone"
            className="form-input"
            placeholder="+1 555 000 0000"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
            maxLength={30}
          />
          <span className="form-hint">Include country code (e.g. +1, +44, +91)</span>
        </div>
      </div>
      <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0, marginTop: '1.5rem' }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={loading}>Cancel</button>
        <button type="submit" className={`btn btn-primary${loading ? ' btn-loading' : ''}`} disabled={loading}>
          {loading ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  );
}

function DeleteConfirm({ contact, onConfirm, onCancel, loading }: {
  contact: Contact; onConfirm: () => void; onCancel: () => void; loading: boolean;
}) {
  return (
    <div>
      <p style={{ fontSize: '0.9375rem', color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
        Are you sure you want to delete <strong>{contact.name}</strong>? This will also delete all follow-ups associated with this contact. This action cannot be undone.
      </p>
      <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0 }}>
        <button className="btn btn-secondary" onClick={onCancel} disabled={loading}>Cancel</button>
        <button
          id="delete-contact-confirm"
          className={`btn btn-danger${loading ? ' btn-loading' : ''}`}
          onClick={onConfirm}
          disabled={loading}
        >
          {loading ? 'Deleting…' : 'Delete contact'}
        </button>
      </div>
    </div>
  );
}

export default function ContactsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<'create' | 'edit' | 'delete' | null>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [mutError, setMutError] = useState('');

  const { data: contacts, isLoading, error } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 500 }),
  });

  const createMut = useMutation({
    mutationFn: contactsApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['contacts'] }); setModal(null); },
    onError: (e) => setMutError(getApiError(e)),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name: string; phone_number: string } }) =>
      contactsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['contacts'] }); setModal(null); },
    onError: (e) => setMutError(getApiError(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => contactsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['contacts'] }); setModal(null); setSelected(null); },
    onError: (e) => setMutError(getApiError(e)),
  });

  const filtered = (contacts ?? []).filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.phone_number.includes(search),
  );

  const openEdit = (c: Contact) => { setSelected(c); setMutError(''); setModal('edit'); };
  const openDelete = (c: Contact) => { setSelected(c); setMutError(''); setModal('delete'); };

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <h1 className="page-title">Contacts</h1>
          <p className="page-subtitle">Manage your customer contact book</p>
        </div>
        <button
          id="add-contact-btn"
          className="btn btn-primary"
          onClick={() => { setMutError(''); setModal('create'); }}
        >
          <Plus size={16} /> Add Contact
        </button>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
          Failed to load contacts: {getApiError(error)}
        </div>
      )}

      {/* Search */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div className="search-bar" style={{ maxWidth: 400 }}>
          <Search size={15} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
          <input
            id="contacts-search"
            placeholder="Search by name or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="loading-overlay"><div className="spinner spinner-lg" /><span>Loading contacts…</span></div>
      ) : error ? null : filtered.length === 0 ? (
        <div className="card">
          <div className="empty-state" style={{ padding: '4rem' }}>
            <div className="empty-state-icon"><Users size={26} /></div>
            <div className="empty-state-title">{search ? 'No contacts match your search' : 'No contacts yet'}</div>
            <div className="empty-state-desc">
              {search ? 'Try a different search term.' : 'Add your first contact to get started.'}
            </div>
            {!search && (
              <button className="btn btn-primary" onClick={() => { setMutError(''); setModal('create'); }}>
                <Plus size={14} /> Add Contact
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone number</th>
                <th>Added</th>
                <th style={{ width: 100 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/contacts/${c.id}`)}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%',
                        background: 'var(--color-brand-100)', color: 'var(--color-brand-700)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 700, fontSize: '0.75rem', flexShrink: 0,
                      }}>
                        {c.name.slice(0, 2).toUpperCase()}
                      </div>
                      <span style={{ fontWeight: 500 }}>{c.name}</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-text-secondary)' }}>
                      <Phone size={13} />
                      <span className="font-mono" style={{ fontSize: '0.8125rem' }}>{c.phone_number}</span>
                    </div>
                  </td>
                  <td style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                    {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button
                        id={`edit-contact-${c.id}`}
                        className="btn btn-ghost btn-icon btn-sm"
                        data-tooltip="Edit"
                        onClick={() => openEdit(c)}
                      ><Edit size={14} /></button>
                      <button
                        id={`delete-contact-${c.id}`}
                        className="btn btn-ghost btn-icon btn-sm"
                        data-tooltip="Delete"
                        style={{ color: 'var(--color-error-500)' }}
                        onClick={() => openDelete(c)}
                      ><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Count */}
      {!isLoading && contacts && (
        <div style={{ marginTop: '0.75rem', fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
          {filtered.length} of {contacts.length} contact{contacts.length !== 1 ? 's' : ''}
        </div>
      )}

      {/* Modals */}
      {modal === 'create' && (
        <div className="dialog-overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Add Contact</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setModal(null)}>✕</button>
            </div>
            <div className="dialog-body">
              <ContactForm
                onSubmit={async (d) => { await createMut.mutateAsync(d); }}
                onCancel={() => setModal(null)}
                loading={createMut.isPending}
                error={mutError}
                submitLabel="Add Contact"
              />
            </div>
          </div>
        </div>
      )}

      {modal === 'edit' && selected && (
        <div className="dialog-overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Edit Contact</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setModal(null)}>✕</button>
            </div>
            <div className="dialog-body">
              <ContactForm
                initial={selected}
                onSubmit={async (d) => { await updateMut.mutateAsync({ id: selected.id, data: d }); }}
                onCancel={() => setModal(null)}
                loading={updateMut.isPending}
                error={mutError}
                submitLabel="Save Changes"
              />
            </div>
          </div>
        </div>
      )}

      {modal === 'delete' && selected && (
        <div className="dialog-overlay" onClick={() => setModal(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">Delete Contact</span>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setModal(null)}>✕</button>
            </div>
            <div className="dialog-body">
              <DeleteConfirm
                contact={selected}
                onConfirm={() => deleteMut.mutate(selected.id)}
                onCancel={() => setModal(null)}
                loading={deleteMut.isPending}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
