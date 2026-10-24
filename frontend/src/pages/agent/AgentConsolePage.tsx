import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Bot, Zap, ChevronRight, Clock, MessageSquare, Sparkles, AlertCircle, Info } from 'lucide-react';
import { agentApi, followUpsApi, contactsApi, getApiError } from '../../lib/api';
import { format, isPast } from 'date-fns';

export default function AgentConsolePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedFuId = searchParams.get('follow_up_id');

  const [followUpId, setFollowUpId] = useState(preselectedFuId ?? '');
  const [customerMessage, setCustomerMessage] = useState('');
  const [error, setError] = useState('');

  const { data: followUps } = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => followUpsApi.list({ limit: 500 }),
  });

  const { data: contacts } = useQuery({
    queryKey: ['contacts'],
    queryFn: () => contactsApi.list({ limit: 500 }),
  });

  const contactMap = new Map((contacts ?? []).map((c) => [c.id, c]));
  const pendingFUs = (followUps ?? []).filter((f) => f.status === 'pending');

  const createRunMut = useMutation({
    mutationFn: () =>
      agentApi.createRun({
        follow_up_id: parseInt(followUpId),
        customer_message: customerMessage.trim() || undefined,
      }),
    onSuccess: (run) => {
      navigate(`/agent/runs/${run.id}`);
    },
    onError: (e) => setError(getApiError(e)),
  });

  const selectedFu = followUps?.find((f) => f.id === parseInt(followUpId));
  const selectedContact = selectedFu ? contactMap.get(selectedFu.contact_id) : null;

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 className="page-title">Agent Console</h1>
        <p className="page-subtitle">
          NudgeFlow AI drafts a WhatsApp follow-up message for your review. You approve before anything happens.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Run form */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
              <div style={{ width: 32, height: 32, borderRadius: 'var(--radius-md)', background: 'var(--color-brand-600)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Bot size={17} color="white" />
              </div>
              <span className="card-title">Start New Run</span>
            </div>
          </div>
          <div className="card-body">
            {error && (
              <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={(e) => { e.preventDefault(); setError(''); createRunMut.mutate(); }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div className="form-group">
                  <label className="form-label form-label-required" htmlFor="agent-followup">
                    Select Follow-up
                  </label>
                  <select
                    id="agent-followup"
                    className="form-select"
                    value={followUpId}
                    onChange={(e) => setFollowUpId(e.target.value)}
                    required
                  >
                    <option value="">Choose a pending follow-up…</option>
                    {pendingFUs.map((fu) => {
                      const c = contactMap.get(fu.contact_id);
                      const overdue = isPast(new Date(fu.due_at));
                      return (
                        <option key={fu.id} value={fu.id}>
                          {overdue ? '⚠ ' : ''}{fu.title} — {c?.name ?? 'Unknown'} ({format(new Date(fu.due_at), 'MMM d')})
                        </option>
                      );
                    })}
                  </select>
                  {pendingFUs.length === 0 && (
                    <span className="form-hint">
                      No pending follow-ups. <Link to="/follow-ups">Add one first.</Link>
                    </span>
                  )}
                </div>

                {selectedFu && selectedContact && (
                  <div className="alert alert-info" style={{ gap: '0.5rem' }}>
                    <Info size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <div style={{ fontWeight: 500 }}>{selectedFu.title}</div>
                      <div style={{ fontSize: '0.8125rem', marginTop: 2 }}>
                        Contact: <strong>{selectedContact.name}</strong> ({selectedContact.phone_number})
                        {selectedFu.notes && <span> · {selectedFu.notes.slice(0, 80)}{selectedFu.notes.length > 80 ? '…' : ''}</span>}
                      </div>
                    </div>
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label" htmlFor="agent-message">
                    Customer message
                    <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>(optional)</span>
                  </label>
                  <textarea
                    id="agent-message"
                    className="form-textarea"
                    placeholder="Paste the customer's latest WhatsApp message here. The agent will extract intent and context to improve the draft."
                    value={customerMessage}
                    onChange={(e) => setCustomerMessage(e.target.value)}
                    rows={4}
                    maxLength={5000}
                  />
                  <span className="form-hint">
                    If provided, the agent will classify the message intent and tailor the draft.
                  </span>
                </div>

                <button
                  id="start-agent-run"
                  type="submit"
                  className={`btn btn-primary${createRunMut.isPending ? ' btn-loading' : ''}`}
                  disabled={createRunMut.isPending || !followUpId}
                  style={{ padding: '0.625rem 1.25rem' }}
                >
                  {createRunMut.isPending ? (
                    'Starting run…'
                  ) : (
                    <><Sparkles size={15} /> Start Agent Run</>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Info panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* How it works */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">How it works</span>
            </div>
            <div className="card-body-sm">
              {[
                { icon: <Zap size={14} />, color: 'var(--color-brand-600)', bg: 'var(--color-brand-50)', step: 'Analyze', desc: 'The agent reads the follow-up context and any customer message you provide.' },
                { icon: <MessageSquare size={14} />, color: 'var(--color-success-600)', bg: 'var(--color-success-50)', step: 'Draft', desc: 'A WhatsApp message is drafted using AI (or a deterministic fallback).' },
                { icon: <ChevronRight size={14} />, color: 'var(--color-warning-600)', bg: 'var(--color-warning-50)', step: 'Review', desc: 'You review the proposed message and explicitly approve or reject it.' },
                { icon: <Bot size={14} />, color: 'var(--color-purple-600)', bg: 'var(--color-purple-50)', step: 'Send (mock)', desc: 'Approved messages are executed via the mock messaging tool. No real WhatsApp is contacted.' },
              ].map(({ icon, color, bg, step, desc }) => (
                <div key={step} style={{ display: 'flex', gap: '0.75rem', paddingBottom: '0.875rem', marginBottom: '0.875rem', borderBottom: '1px solid var(--color-gray-100)' }}>
                  <div style={{ width: 28, height: 28, borderRadius: 'var(--radius-sm)', background: bg, color, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1 }}>
                    {icon}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.8125rem' }}>{step}</div>
                    <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>{desc}</div>
                  </div>
                </div>
              )).slice(0, 3)}
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ width: 28, height: 28, borderRadius: 'var(--radius-sm)', background: 'var(--color-purple-50)', color: 'var(--color-purple-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 1 }}>
                  <Bot size={14} />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.8125rem' }}>Send (mock)</div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>Approved messages are executed via the mock messaging tool. No real WhatsApp is contacted.</div>
                </div>
              </div>
            </div>
          </div>

          {/* Safety notice */}
          <div className="alert alert-warning" style={{ alignItems: 'flex-start' }}>
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ fontSize: '0.8125rem' }}>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>No real messages sent</div>
              The current integration uses a mock tool. No actual WhatsApp messages are delivered. Approval is always a manual human action.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
