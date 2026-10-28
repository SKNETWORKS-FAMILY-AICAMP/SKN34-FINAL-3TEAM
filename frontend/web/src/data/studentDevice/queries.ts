import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { studentDeviceApi } from './api.ts'

export const qrDemoEnabled = import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true' &&
  import.meta.env.VITE_SHARED_DEVICE_MOCK === 'true'

export function usePairingOrigins() {
  return useQuery({
    queryKey: ['device-demo-addresses'], enabled: qrDemoEnabled, retry: false, staleTime: Infinity,
    queryFn: async () => {
      if (import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true' &&
          import.meta.env.VITE_SHARED_DEVICE_MOCK === 'true')
        return (await import('../../mocks/sharedDevice.ts')).deviceDemoConfig()
      return null
    },
  })
}

/** 자녀 기기: 이 기기에 등록된 프로필. 미등록 기기는 401 STUDENT_DEVICE_INVALID. */
export function useDeviceProfiles() {
  return useQuery({
    queryKey: ['student-device', 'profiles'],
    queryFn: ({ signal }) => studentDeviceApi.profiles(signal),
    retry: false,
  })
}

export function useDeviceRegistration(onRegistered?: () => void) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ code, label }: { code: string; label: string }) =>
      studentDeviceApi.register(code, label),
    onSuccess: () => {
      // 프로필 재조회가 등록 폼을 제거하기 전에 완료 안내와 QR 주소 정리를 실행한다.
      onRegistered?.()
      return cache.invalidateQueries({ queryKey: ['student-device'] })
    },
  })
}

export function usePinLogin() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ childId, pin }: { childId: string; pin: string }) =>
      studentDeviceApi.login(childId, pin),
    // 실패 횟수·잠금이 바뀌므로 프로필을 다시 받는다. 성공 시에는 학생 데이터만 새로 받도록 캐시를 비운다.
    onError: () => cache.invalidateQueries({ queryKey: ['student-device', 'profiles'] }),
  })
}

/** 학부모: 등록 기기 목록 */
export function useStudentDevices() {
  return useQuery({
    queryKey: ['parent', 'student-devices'],
    queryFn: ({ signal }) => studentDeviceApi.devices(signal),
    retry: false,
    refetchInterval: qrDemoEnabled ? 3000 : false,
  })
}

export function useDeviceAdmin() {
  const cache = useQueryClient()
  const refresh = () => {
    void cache.invalidateQueries({ queryKey: ['parent'] })
    void cache.invalidateQueries({ queryKey: ['children'] })
  }
  return {
    pairing: useMutation({
      mutationFn: (childIds: string[]) => studentDeviceApi.createPairing(childIds),
    }),
    revoke: useMutation({
      mutationFn: (deviceId: string) => studentDeviceApi.revoke(deviceId),
      onSuccess: refresh,
    }),
    setPin: useMutation({
      mutationFn: ({ childId, pin, reauthToken }: { childId: string; pin: string; reauthToken: string }) =>
        studentDeviceApi.setPin(childId, pin, reauthToken),
      onSuccess: refresh,
    }),
  }
}
