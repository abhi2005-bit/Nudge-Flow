import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, CheckCircle, XCircle, RotateCcw, Zap, Bot, Clock, AlertTriangle,
  Shield, MessageSquare, Brain, Database, Eye, AlertCircle, Info, Activity,
} from 'lucide-react';
import { agentApi, getApiError, type AgentRun, type AgentRunStatus } from '../../lib/api';
import { format, formatDistanceToNow } from 'date-fns';

// ── Status helpers ──────────────────────────────────────────────────────────

function statusColor(status: AgentRunStatus) {
  switch (status) {
    case 'awaiting_approval': return { bg: 'var(--color-warning-50)', border: 'var(--color-warning-200)', text: 'var(--color-warning-700)' };
    case 'rejected':          return { bg: 'var(--color-error-50)',   border: 'var(--color-error-200)',   text: 'var(--color-error-700)'   };
    case 'executing':         return { bg: 'var(--color-brand-50)',   border: 'var(--color-brand-200)',   text: 'var(--color-brand-700)'   };
    case 'completed':         return { bg: 'var(--color-success-50)', border: 'var(--color-success-200)', text: 'var(--color-success-700)' };
    case 'failed':            return { bg: 'var(--color-error-50)',   border: 'var(--color-error-200)',   text: 'var(--color-error-700)'   };
    case 'ready_to_execute':  return { bg: 'var(--color-purple-50)',  border: 'var(--color-purple-200)',  text: 'var(--color-purple-600)'  };
    case 'outcome_uncertain': return { bg: 'var(--color-orange-50)',  border: 'var(--color-orange-200)',  text: 'var(--color-orange-600)'  };
  }
}

function statusLabel(status: AgentRunStatus) {
  switch (status) {
    case 'awaiting_approval': return 'Awaiting Approval';
    case 'rejected':          return 'Rejected';
    case 'executing':         return 'Executing';
    case 'completed':         return 'Completed';
    case 'failed':            return 'Failed';
    case 'ready_to_execute':  return 'Ready to Execute';
    case 'outcome_uncertain': return 'Outcome Uncertain';
  }
}

function statusIcon(status: AgentRunStatus) {
  switch (status) {
    case 'awaiting_approval': return <Clock size={16} />;
    case 'rejected':          return <XCircle size={16} />;
    case 'executing':         return <Zap size={16} />;
    case 'completed':         return <CheckCircle size={16} />;
    case 'failed':            return <AlertCircle size={16} />;
    case 'ready_to_execute':  return <Zap size={16} />;
    case 'outcome_uncertain': return <AlertTriangle size={16} />;
  }
}

function intentLabel(intent: string) {
  switch (intent) {
    case 'booking_enquiry':  return 'Booking Enquiry';
    case 'purchase_enquiry': return 'Purchase Enquiry';
    case 'service_enquiry':  return 'Service Enquiry';
    case 'complaint_support':return 'Complaint / Support';
    case 'cancellation':     return 'Cancellation';
    case 'other_uncertain':  return 'Other / Uncertain';
    default:                 return intent;
  }
}

// ── Action bar ──────────────────────────────────────────────────────────────

function ActionBar({ run, onAction, actionPending }: {
  run: AgentRun;
  onAction: (action: string, reason?: string) => void;
  actionPending: boolean;
}) {
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  if (run.status === 'awaiting_approval') {
    return (
      <>
        <div
          style={{
            background: 'linear-gradient(135deg, var(--color-brand-50) 0%, var(--color-purple-50) 100%)',
            border: '1px solid var(--color-brand-200)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem 1.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontWeight: 600, color: 'var(--color-brand-900)', marginBottom: 4 }}>
              Your review is required
            </div>
            <div style={{ fontSize: '0.8125rem', color: 'var(--color-brand-700)' }}>
              Review the proposed message below. Approve to execute via the mock messaging tool, or reject to discard this run.
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              id="reject-run-btn"
              className="btn btn-secondary"
              onClick={() => setShowRejectModal(true)}
              disabled={actionPending}
            >
              <XCircle size={15} /> Reject
            </button>
            <button
              id="approve-run-btn"
              className={`btn btn-success${actionPending ? ' btn-loading' : ''}`}
              onClick={() => onAction('approve')}
              disabled={actionPending}
            >
              <CheckCircle size={15} /> Approve & Send
            </button>
          </div>
        </div>

        {showRejectModal && (
          <div className="dialog-overlay" onClick={() => setShowRejectModal(false)}>
            <div className="dialog" onClick={(e) => e.stopPropagation()}>
              <div className="dialog-header">
                <span className="dialog-title">Reject Run</span>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setShowRejectModal(false)}>✕</button>
              </div>
              <div className="dialog-body">
                <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
                  Provide an optional reason for rejecting this run.
                </p>
                <div className="form-group">
                  <label className="form-label">Reason <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}>(optional)</span></label>
                  <textarea
                    id="reject-reason"
                    className="form-textarea"
                    placeholder="e.g. Tone is too formal, wrong contact selected…"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    maxLength={500}
                    rows={3}
                  />
                </div>
                <div className="dialog-footer" style={{ paddingLeft: 0, paddingRight: 0, paddingBottom: 0, marginTop: '1.25rem' }}>
                  <button className="btn btn-secondary" onClick={() => setShowRejectModal(false)}>Cancel</button>
                  <button
                    id="confirm-reject-btn"
                    className={`btn btn-danger${actionPending ? ' btn-loading' : ''}`}
                    onClick={() => { onAction('reject', rejectReason); setShowRejectModal(false); }}
                    disabled={actionPending}
                  >
                    {actionPending ? 'Rejecting…' : 'Confirm Reject'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  if (run.status === 'ready_to_execute') {
    return (
      <div
        style={{
          background: 'var(--color-purple-50)',
          border: '1px solid var(--color-purple-200)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontWeight: 600, color: 'var(--color-purple-700)', marginBottom: 4 }}>
            Ready to execute
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-purple-600)' }}>
            This run was previously recovered. Execute to attempt the mock messaging step again.
          </div>
        </div>
        <button
          id="execute-run-btn"
          className={`btn btn-primary${actionPending ? ' btn-loading' : ''}`}
          onClick={() => onAction('execute')}
          disabled={actionPending}
        >
          <Zap size={15} /> Execute
        </button>
      </div>
    );
  }

  if (run.status === 'failed') {
    return (
      <div
        style={{
          background: 'var(--color-error-50)',
          border: '1px solid var(--color-error-200)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontWeight: 600, color: 'var(--color-error-700)', marginBottom: 4 }}>
            Execution failed
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-error-600)' }}>
            The run failed during execution. You can attempt to recover it, which will reset its state for a fresh execution.
          </div>
        </div>
        <button
          id="recover-run-btn"
          className={`btn btn-secondary${actionPending ? ' btn-loading' : ''}`}
          onClick={() => onAction('recover')}
          disabled={actionPending}
        >
          <RotateCcw size={15} /> Recover Run
        </button>
      </div>
    );
  }

  if (run.status === 'outcome_uncertain') {
    return (
      <div
        style={{
          background: 'var(--color-orange-50)',
          border: '1px solid var(--color-orange-200)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.25rem 1.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <AlertTriangle size={16} style={{ color: 'var(--color-orange-600)' }} />
          <div style={{ fontWeight: 600, color: 'var(--color-orange-700)' }}>Outcome uncertain — manual verification required</div>
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--color-orange-600)', marginBottom: '0.875rem' }}>
          The mock messaging tool executed but the outcome could not be confirmed. Do not automatically resend. Verify the delivery status with your messaging provider before taking any further action.
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--color-orange-700)', fontWeight: 500 }}>
          Check the Execution Result section below for details.
        </div>
      </div>
    );
  }

  return null;
}

// ── Main component ──────────────────────────────────────────────────────────

export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const qc = useQueryClient();
  const id = parseInt(runId ?? '0');
  const [actionError, setActionError] = useState('');

  const { data: run, isLoading, error } = useQuery({
    queryKey: ['agent-run', id],
    queryFn: () => agentApi.getRun(id),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data?.status === 'executing' ? 3000 : false,
  });

  const actionMut = useMutation({
    mutationFn: ({ action, reason }: { action: string; reason?: string }) => {
      if (action === 'approve') return agentApi.approve(id);
      if (action === 'reject')  return agentApi.reject(id, reason);
      if (action === 'recover') return agentApi.recover(id);
      if (action === 'execute') return agentApi.execute(id);
      throw new Error('Unknown action');
    },
    onSuccess: (updated) => {
      qc.setQueryData(['agent-run', id], updated);
      setActionError('');
    },
    onError: (e) => setActionError(getApiError(e)),
  });

  if (isLoading) {
    return <div className="loading-overlay"><div className="spinner spinner-lg" /><span>Loading run…</span></div>;
  }

  if (error || !run) {
    return (
      <div style={{ padding: 'var(--space-6)' }}>
        <div className="alert alert-error">Agent run not found.</div>
        <Link to="/agent" className="btn btn-secondary" style={{ marginTop: '1rem' }}>
          <ArrowLeft size={14} /> Back to Console
        </Link>
      </div>
    );
  }

  const sc = statusColor(run.status);

  return (
    <div style={{ padding: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1.5rem' }}>
        <Link to="/agent" className="btn btn-ghost btn-icon btn-sm" style={{ marginTop: 4 }}>
          <ArrowLeft size={16} />
        </Link>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.375rem' }}>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Run #{run.id}</h1>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.375rem',
              padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-full)',
              background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text,
              fontWeight: 600, fontSize: '0.8125rem',
            }}>
              {statusIcon(run.status)}
              {statusLabel(run.status)}
            </div>
            {run.status === 'executing' && (
              <div className="spinner spinner-sm" style={{ borderTopColor: 'var(--color-brand-600)' }} />
            )}
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
            Follow-up #{run.follow_up_id} · Created {formatDistanceToNow(new Date(run.created_at), { addSuffix: true })}
          </div>
        </div>
      </div>

      {/* Action error */}
      {actionError && (
        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={15} style={{ flexShrink: 0 }} />
          <span>{actionError}</span>
        </div>
      )}

      {/* Action bar */}
      <div style={{ marginBottom: '1.5rem' }}>
        <ActionBar
          run={run}
          onAction={(action, reason) => actionMut.mutate({ action, reason })}
          actionPending={actionMut.isPending}
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Proposed message */}
          <div className="card">
            <div className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <MessageSquare size={16} style={{ color: 'var(--color-brand-600)' }} />
                <span className="card-title">Proposed Message</span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {run.draft.source === 'llm' ? (
                  <span className="badge badge-blue"><Brain size={10} /> AI-generated</span>
                ) : (
                  <span className="badge badge-yellow"><Database size={10} /> Deterministic fallback</span>
                )}
              </div>
            </div>
            <div className="card-body">
              <div className={`message-box ${run.draft.source === 'llm' ? 'draft-llm' : 'draft-fallback'}`}>
                {run.proposed_message}
              </div>
              {run.draft.source === 'deterministic' && (
                <div className="alert alert-warning" style={{ marginTop: '0.75rem', fontSize: '0.8125rem' }}>
                  <Info size={13} style={{ flexShrink: 0 }} />
                  This is a deterministic template — the AI draft was unavailable. Review carefully before approving.
                </div>
              )}
            </div>
          </div>

          {/* Execution result */}
          {run.execution && (
            <div className="card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={16} style={{ color: run.execution.status === 'succeeded' ? 'var(--color-success-600)' : run.execution.status === 'uncertain' ? 'var(--color-orange-600)' : 'var(--color-error-600)' }} />
                  <span className="card-title">Execution Result</span>
                </div>
                <span className={`badge ${run.execution.status === 'succeeded' ? 'badge-green' : run.execution.status === 'uncertain' ? 'badge-orange' : 'badge-red'}`}>
                  {run.execution.status}
                </span>
              </div>
              <div className="card-body-sm">
                <div className="detail-row">
                  <span className="detail-label">Tool</span>
                  <span className="detail-value font-mono">{run.execution.tool_name}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Status</span>
                  <span className="detail-value">
                    {run.execution.status === 'succeeded'
                      ? <span style={{ color: 'var(--color-success-600)', fontWeight: 500 }}>Succeeded</span>
                      : run.execution.status === 'uncertain'
                      ? <span style={{ color: 'var(--color-orange-600)', fontWeight: 500 }}>Uncertain — verify manually</span>
                      : <span style={{ color: 'var(--color-error-600)', fontWeight: 500 }}>Failed</span>}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Executed at</span>
                  <span className="detail-value">{format(new Date(run.execution.executed_at), 'PPPp')}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Verified</span>
                  <span className="detail-value">
                    {run.execution.verified
                      ? <span style={{ color: 'var(--color-success-600)' }}><CheckCircle size={13} style={{ display: 'inline' }} /> Yes — {run.execution.verified_at ? format(new Date(run.execution.verified_at), 'PPPp') : ''}</span>
                      : <span style={{ color: 'var(--color-text-muted)' }}>Not verified</span>}
                  </span>
                </div>
                {run.execution.error_code && (
                  <div className="detail-row">
                    <span className="detail-label">Error code</span>
                    <span className="detail-value font-mono" style={{ color: 'var(--color-error-600)' }}>{run.execution.error_code}</span>
                  </div>
                )}
                <div className="detail-row" style={{ border: 'none' }}>
                  <span className="detail-label">Result</span>
                  <div className="detail-value">
                    <pre style={{ margin: 0, fontSize: '0.75rem', background: 'var(--color-gray-50)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', overflow: 'auto' }}>
                      {JSON.stringify(run.execution.result, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Audit timeline */}
          {run.audit.length > 0 && (
            <div className="card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Shield size={16} style={{ color: 'var(--color-gray-500)' }} />
                  <span className="card-title">Audit History</span>
                </div>
                <span className="badge badge-gray">{run.audit.length} event{run.audit.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="card-body">
                <div className="audit-timeline">
                  {run.audit.slice().reverse().map((event) => (
                    <div key={event.id} className="audit-event">
                      <div className="audit-dot">
                        <Activity size={12} style={{ color: 'var(--color-gray-500)' }} />
                      </div>
                      <div className="audit-content">
                        <div className="audit-action">{event.action}</div>
                        <div className="audit-time">
                          {format(new Date(event.created_at), 'PPPp')}
                          {event.actor_user_id && (
                            <span style={{ marginLeft: 6 }}>· User #{event.actor_user_id}</span>
                          )}
                        </div>
                        {Object.keys(event.details).length > 0 && (
                          <div className="audit-details">
                            <pre style={{ margin: 0, fontSize: '0.75rem' }}>
                              {JSON.stringify(event.details, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Run info */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Run Details</span>
            </div>
            <div className="card-body-sm">
              <div className="detail-row">
                <span className="detail-label">Run ID</span>
                <span className="detail-value font-mono">#{run.id}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Follow-up</span>
                <span className="detail-value">
                  <Link to={`/follow-ups/${run.follow_up_id}`} style={{ color: 'var(--color-brand-600)' }}>
                    #{run.follow_up_id}
                  </Link>
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Tool</span>
                <span className="detail-value font-mono" style={{ fontSize: '0.8125rem' }}>{run.tool_name}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Approval</span>
                <span className="detail-value">
                  {run.approval_decision === 'approved'
                    ? <span className="badge badge-green"><CheckCircle size={10} /> Approved</span>
                    : run.approval_decision === 'rejected'
                    ? <span className="badge badge-red"><XCircle size={10} /> Rejected</span>
                    : <span style={{ color: 'var(--color-text-muted)' }}>Pending</span>}
                </span>
              </div>
              {run.rejection_reason && (
                <div className="detail-row">
                  <span className="detail-label">Reject reason</span>
                  <span className="detail-value" style={{ color: 'var(--color-error-600)' }}>{run.rejection_reason}</span>
                </div>
              )}
              <div className="detail-row">
                <span className="detail-label">Created</span>
                <span className="detail-value">{format(new Date(run.created_at), 'PPPp')}</span>
              </div>
              <div className="detail-row" style={{ border: 'none' }}>
                <span className="detail-label">Updated</span>
                <span className="detail-value">{format(new Date(run.updated_at), 'PPPp')}</span>
              </div>
            </div>
          </div>

          {/* Intent classification */}
          <div className="card">
            <div className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Brain size={15} style={{ color: 'var(--color-brand-600)' }} />
                <span className="card-title">Intent Classification</span>
              </div>
              <span className={`badge ${run.intent_classification.status === 'classified' ? 'badge-blue' : run.intent_classification.status === 'not_performed' ? 'badge-gray' : 'badge-yellow'}`}>
                {run.intent_classification.status}
              </span>
            </div>
            <div className="card-body-sm">
              {run.intent_classification.status === 'classified' ? (
                <>
                  <div className="detail-row">
                    <span className="detail-label">Intent</span>
                    <span className="detail-value font-medium">{intentLabel(run.intent_classification.intent ?? '')}</span>
                  </div>
                  {run.intent_classification.confidence !== null && (
                    <div className="detail-row">
                      <span className="detail-label">Confidence</span>
                      <div className="detail-value" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{ flex: 1, height: 6, background: 'var(--color-gray-200)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${(run.intent_classification.confidence ?? 0) * 100}%`, height: '100%', background: 'var(--color-brand-500)' }} />
                        </div>
                        <span style={{ fontSize: '0.8125rem', fontWeight: 500 }}>
                          {Math.round((run.intent_classification.confidence ?? 0) * 100)}%
                        </span>
                      </div>
                    </div>
                  )}
                </>
              ) : run.intent_classification.status === 'not_performed' ? (
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', padding: '0.25rem 0' }}>
                  No customer message was provided; classification skipped.
                </div>
              ) : (
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-error-600)' }}>
                  {run.intent_classification.error_code
                    ? `Error: ${run.intent_classification.error_code}`
                    : 'Classification unavailable.'}
                </div>
              )}
            </div>
          </div>

          {/* Message extraction */}
          <div className="card">
            <div className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Eye size={15} style={{ color: 'var(--color-purple-600)' }} />
                <span className="card-title">Message Extraction</span>
              </div>
              <span className={`badge ${run.message_extraction.status === 'completed' ? 'badge-blue' : run.message_extraction.status === 'not_performed' ? 'badge-gray' : 'badge-yellow'}`}>
                {run.message_extraction.status}
              </span>
            </div>
            <div className="card-body-sm">
              {run.message_extraction.status === 'completed' && run.message_extraction.data ? (
                <>
                  {Object.entries(run.message_extraction.data).map(([key, val]) => {
                    if (key === 'other_details' || key === 'missing_information') {
                      const arr = val as string[];
                      if (!arr.length) return null;
                      return (
                        <div key={key} className="detail-row">
                          <span className="detail-label" style={{ textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                          <div className="detail-value">
                            {arr.map((s, i) => <div key={i} style={{ fontSize: '0.8125rem' }}>· {s}</div>)}
                          </div>
                        </div>
                      );
                    }
                    if (!val) return null;
                    return (
                      <div key={key} className="detail-row">
                        <span className="detail-label" style={{ textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                        <span className="detail-value" style={{ fontSize: '0.8125rem' }}>{String(val)}</span>
                      </div>
                    );
                  })}
                </>
              ) : run.message_extraction.status === 'not_performed' ? (
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', padding: '0.25rem 0' }}>
                  No customer message was provided; extraction skipped.
                </div>
              ) : (
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                  {run.message_extraction.error_code ?? 'Extraction unavailable.'}
                </div>
              )}
            </div>
          </div>

          {/* Draft info */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Draft Info</span>
            </div>
            <div className="card-body-sm">
              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className={`badge ${run.draft.status === 'generated' ? 'badge-blue' : 'badge-yellow'}`}>
                  {run.draft.status}
                </span>
              </div>
              <div className="detail-row" style={{ border: 'none' }}>
                <span className="detail-label">Source</span>
                <span className="detail-value">
                  {run.draft.source === 'llm'
                    ? <span style={{ color: 'var(--color-brand-700)', fontWeight: 500 }}>🤖 LLM-generated</span>
                    : <span style={{ color: 'var(--color-warning-700)', fontWeight: 500 }}>🔧 Deterministic template</span>}
                </span>
              </div>
              {run.draft.error_code && (
                <div className="detail-row">
                  <span className="detail-label">Error</span>
                  <span className="detail-value font-mono" style={{ color: 'var(--color-error-600)', fontSize: '0.8125rem' }}>
                    {run.draft.error_code}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
