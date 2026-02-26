import { useQuery, useMutation } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  Vehicle,
  Session,
  Message,
  Signal,
  QueryRequest,
  QueryResponse,
  HealthResponse,
} from './types';

// Query keys factory
export const queryKeys = {
  health: ['health'] as const,
  vehicles: ['vehicles'] as const,
  sessions: (vehicleId: string) => ['vehicles', vehicleId, 'sessions'] as const,
  messages: (vehicleId: string) => ['vehicles', vehicleId, 'messages'] as const,
  signals: (vehicleId: string, messageName: string) =>
    ['vehicles', vehicleId, 'messages', messageName, 'signals'] as const,
};

// Health check
export const useHealth = () => {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const { data } = await apiClient.get<HealthResponse>('/health');
      return data;
    },
    refetchInterval: 60000, // Check every minute
  });
};

// List vehicles
export const useVehicles = () => {
  return useQuery({
    queryKey: queryKeys.vehicles,
    queryFn: async () => {
      const { data } = await apiClient.get<Vehicle[]>('/vehicles');
      return data;
    },
    staleTime: 30000, // 30 seconds
  });
};

// Get sessions for vehicle
export const useSessions = (vehicleId: string | null) => {
  return useQuery({
    queryKey: queryKeys.sessions(vehicleId!),
    queryFn: async () => {
      const { data } = await apiClient.get<Session[]>(
        `/vehicles/${vehicleId}/sessions`
      );
      return data;
    },
    enabled: !!vehicleId,
    staleTime: 30000,
  });
};

// Get messages for vehicle
export const useMessages = (vehicleId: string | null) => {
  return useQuery({
    queryKey: queryKeys.messages(vehicleId!),
    queryFn: async () => {
      const { data } = await apiClient.get<Message[]>(
        `/vehicles/${vehicleId}/messages`
      );
      return data;
    },
    enabled: !!vehicleId,
    staleTime: 30000,
  });
};

// Get signals for message
export const useSignals = (vehicleId: string | null, messageName: string | null) => {
  return useQuery({
    queryKey: queryKeys.signals(vehicleId!, messageName!),
    queryFn: async () => {
      const { data} = await apiClient.get<Signal[]>(
        `/vehicles/${vehicleId}/messages/${messageName}/signals`
      );
      return data;
    },
    enabled: !!(vehicleId && messageName),
    staleTime: 60000, // 1 minute
  });
};

// Query time-series data (mutation for POST)
export const useQuerySignals = () => {
  return useMutation({
    mutationFn: async ({
      vehicleId,
      request,
    }: {
      vehicleId: string;
      request: QueryRequest;
    }) => {
      const { data } = await apiClient.post<QueryResponse>(
        `/vehicles/${vehicleId}/query`,
        request
      );
      return data;
    },
  });
};
