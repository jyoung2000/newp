import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { qk } from './queryKeys'
import type {
  DeviceOut,
  ExtensionInfo,
  FileOut,
  ProfileFull,
  RunOut,
  SourceInfo,
  UserSettings,
} from './types'

// Shared read queries used by more than one route.

export function useProfile() {
  return useQuery({
    queryKey: qk.profile,
    queryFn: () => api.get<ProfileFull>('/api/profile'),
  })
}

export function useFiles() {
  return useQuery({
    queryKey: qk.files,
    queryFn: () => api.get<FileOut[]>('/api/files'),
  })
}

export function useUserSettings() {
  return useQuery({
    queryKey: qk.settings,
    queryFn: () => api.get<UserSettings>('/api/auth/settings'),
  })
}

export function useDevices() {
  return useQuery({
    queryKey: qk.devices,
    queryFn: () => api.get<DeviceOut[]>('/api/devices'),
  })
}

export function useSources() {
  return useQuery({
    queryKey: qk.sources,
    queryFn: () => api.get<SourceInfo[]>('/api/search/sources'),
  })
}

export function useExtensionInfo() {
  return useQuery({
    queryKey: qk.extensionInfo,
    queryFn: () => api.get<ExtensionInfo>('/api/files/extension/info'),
  })
}

export function useRuns() {
  return useQuery({
    queryKey: qk.runs,
    queryFn: () => api.get<RunOut[]>('/api/runs'),
    refetchInterval: 8000,
  })
}
