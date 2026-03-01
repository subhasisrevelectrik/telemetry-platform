/**
 * API client for the chat endpoints.
 *
 * POST /chat         → starts an async job, returns {job_id} immediately
 * GET  /chat/status  → polls for the result (pending | complete | error)
 *
 * Both calls go through the normal API Gateway client. Because POST /chat
 * returns in < 1 second, there is no timeout issue.
 */
import { apiClient } from '@/api/client';
import type {
  ChatRequest,
  ChatStartResponse,
  JobStatusResponse,
  UsageStats,
} from './chatTypes';

export async function startChat(req: ChatRequest): Promise<ChatStartResponse> {
  const { data } = await apiClient.post<ChatStartResponse>('/chat', req);
  return data;
}

export async function pollChatStatus(jobId: string): Promise<JobStatusResponse> {
  const { data } = await apiClient.get<JobStatusResponse>(`/chat/status/${jobId}`);
  return data;
}

export async function fetchUsageStats(): Promise<UsageStats> {
  const { data } = await apiClient.get<UsageStats>('/chat/usage');
  return data;
}
