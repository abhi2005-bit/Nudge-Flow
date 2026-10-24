/**
 * NudgeFlow AI — Centralized API client
 * All requests flow through this module. Never import axios elsewhere.
 */
import axios, { AxiosError } from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ── Auth token management ─────────────────────────────────────────────────────

const TOKEN_KEY = 'nf_access_token';

export const tokenStorage = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string): void => localStorage.setItem(TOKEN_KEY, token),
  clear: (): void => localStorage.removeItem(TOKEN_KEY),
};

// Attach bearer token on every request
api.interceptors.request.use((config) => {
  const token = tokenStorage.get();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401 on protected requests, clear credentials and emit a custom event so React can redirect
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const url = error.config?.url ?? '';
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register');
    if (error.response?.status === 401 && !isAuthEndpoint && tokenStorage.get()) {
      tokenStorage.clear();
      window.dispatchEvent(new Event('nf:session-expired'));
    }
    return Promise.reject(error);
  },
);

// ── Helper to extract error detail from FastAPI responses ─────────────────────

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => d.msg ?? JSON.stringify(d))
        .join('; ');
    }
    if (error.response?.status === 503) return 'Service is temporarily unavailable.';
    if (error.response?.status === 409) return 'Conflict: the resource already exists.';
    if (!error.response) return 'Network error — is the server running?';
  }
  return 'An unexpected error occurred.';
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  email: string;
  created_at: string;
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data),

  register: (email: string, password: string, business_name: string) =>
    api
      .post<UserResponse>('/auth/register', { email, password, business_name })
      .then((r) => r.data),
};

// ── Contacts ──────────────────────────────────────────────────────────────────

export interface Contact {
  id: number;
  name: string;
  phone_number: string;
  created_at: string;
}

export interface ContactCreate {
  name: string;
  phone_number: string;
}

export interface ContactUpdate {
  name?: string;
  phone_number?: string;
}

export const contactsApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<Contact[]>('/contacts', { params }).then((r) => r.data),

  get: (id: number) =>
    api.get<Contact>(`/contacts/${id}`).then((r) => r.data),

  create: (data: ContactCreate) =>
    api.post<Contact>('/contacts', data).then((r) => r.data),

  update: (id: number, data: ContactUpdate) =>
    api.put<Contact>(`/contacts/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/contacts/${id}`),
};

// ── Follow-ups ────────────────────────────────────────────────────────────────

export type FollowUpStatus = 'pending' | 'completed';

export interface FollowUp {
  id: number;
  contact_id: number;
  title: string;
  notes: string | null;
  due_at: string;
  status: FollowUpStatus;
  created_at: string;
}

export interface FollowUpCreate {
  contact_id: number;
  title: string;
  notes?: string;
  due_at: string;
  status?: FollowUpStatus;
}

export interface FollowUpUpdate {
  title?: string;
  notes?: string;
  due_at?: string;
  status?: FollowUpStatus;
}

export const followUpsApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<FollowUp[]>('/follow-ups', { params }).then((r) => r.data),

  get: (id: number) =>
    api.get<FollowUp>(`/follow-ups/${id}`).then((r) => r.data),

  create: (data: FollowUpCreate) =>
    api.post<FollowUp>('/follow-ups', data).then((r) => r.data),

  update: (id: number, data: FollowUpUpdate) =>
    api.patch<FollowUp>(`/follow-ups/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/follow-ups/${id}`),
};

// ── Agent Runs ────────────────────────────────────────────────────────────────

export type AgentRunStatus =
  | 'awaiting_approval'
  | 'rejected'
  | 'executing'
  | 'completed'
  | 'failed'
  | 'ready_to_execute'
  | 'outcome_uncertain';

export type IntentLabel =
  | 'booking_enquiry'
  | 'purchase_enquiry'
  | 'service_enquiry'
  | 'complaint_support'
  | 'cancellation'
  | 'other_uncertain';

export type IntentClassificationStatus =
  | 'classified'
  | 'not_performed'
  | 'unavailable'
  | 'error';

export interface AgentPlan {
  follow_up_id: number;
  intended_action: 'send_follow_up_message';
  message: string;
  tool_name: 'mock_messaging';
}

export interface AgentExecution {
  id: number;
  tool_name: string;
  status: 'succeeded' | 'failed' | 'uncertain';
  result: Record<string, unknown>;
  error_code: string | null;
  verified: boolean;
  executed_at: string;
  verified_at: string | null;
}

export interface AgentAuditEvent {
  id: number;
  action: string;
  actor_user_id: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface IntentClassification {
  status: IntentClassificationStatus;
  reason: 'missing_input' | null;
  intent: IntentLabel | null;
  confidence: number | null;
  error_code: string | null;
}

export interface MessageExtractionData {
  request_summary: string | null;
  requested_action: string | null;
  product_or_service: string | null;
  date_or_time_mentioned: string | null;
  quantity: string | null;
  budget: string | null;
  other_details: string[];
  missing_information: string[];
}

export interface MessageExtraction {
  status: 'completed' | 'not_performed' | 'unavailable' | 'failed';
  data: MessageExtractionData | null;
  error_code: string | null;
}

export interface DraftInfo {
  status: 'generated' | 'fallback';
  source: 'llm' | 'deterministic';
  error_code: string | null;
}

export interface AgentRun {
  id: number;
  follow_up_id: number;
  status: AgentRunStatus;
  plan: AgentPlan;
  tool_name: string;
  proposed_message: string;
  intent_classification: IntentClassification;
  message_extraction: MessageExtraction;
  draft: DraftInfo;
  approval_decision: 'approved' | 'rejected' | null;
  approval_by_user_id: number | null;
  approval_at: string | null;
  rejection_reason: string | null;
  execution_lease_expires_at: string | null;
  tool_invocation_started_at: string | null;
  created_at: string;
  updated_at: string;
  execution: AgentExecution | null;
  audit: AgentAuditEvent[];
}

export interface AgentRunCreate {
  follow_up_id: number;
  customer_message?: string;
}

export const agentApi = {
  createRun: (data: AgentRunCreate) =>
    api.post<AgentRun>('/agent/runs', data).then((r) => r.data),

  getRun: (runId: number) =>
    api.get<AgentRun>(`/agent/runs/${runId}`).then((r) => r.data),

  approve: (runId: number) =>
    api.post<AgentRun>(`/agent/runs/${runId}/approve`).then((r) => r.data),

  reject: (runId: number, reason?: string) =>
    api
      .post<AgentRun>(`/agent/runs/${runId}/reject`, { reason: reason ?? null })
      .then((r) => r.data),

  recover: (runId: number) =>
    api.post<AgentRun>(`/agent/runs/${runId}/recover`).then((r) => r.data),

  execute: (runId: number) =>
    api.post<AgentRun>(`/agent/runs/${runId}/execute`).then((r) => r.data),
};
