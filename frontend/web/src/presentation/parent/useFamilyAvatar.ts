import { useEffect, useState } from 'react'
import { familyAvatar, saveFamilyAvatar } from '../../data/parent/familyAvatar.ts'
import type { FriendId } from '../../domain/studentLook.ts'

export function useFamilyAvatar(parentId: string, childId: string) {
  const [friend, setFriend] = useState(() => familyAvatar(parentId, childId))
  useEffect(() => {
    const refresh = () => setFriend(familyAvatar(parentId, childId))
    window.addEventListener('storage', refresh)
    window.addEventListener('sagomungchi:family-avatar-changed', refresh)
    return () => { window.removeEventListener('storage', refresh); window.removeEventListener('sagomungchi:family-avatar-changed', refresh) }
  }, [parentId, childId])
  return [friend, (choice: FriendId) => saveFamilyAvatar(parentId, childId, choice)] as const
}
