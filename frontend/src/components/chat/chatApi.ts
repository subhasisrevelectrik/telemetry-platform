/**
 * API client for the /chat endpoint.
 * Uses the existing apiClient instance so base URL and interceptors are shared.
 */
import { apiClient } from '@/api/client';
import type { ChatApiResponse, ChatRequest, UsageStats } from './chatTypes';

export async function sendChatMessage(req: ChatRequest): Promise<ChatApiResponse> {
  const { data } = await apiClient.post<ChatApiResponse>('/chat', req, {
    timeout: 90000, // 90 s — AI calls take longer than normal queries
  });
  return data;
}

export async function fetchUsageStats(): Promise<UsageStats> {
  const { data } = await apiClient.get<UsageStats>('/chat/usage');
  return data;
}
