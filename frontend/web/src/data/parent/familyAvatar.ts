import { FRIENDS, isFriendId } from '../../domain/studentLook.ts'
import type { FriendId } from '../../domain/studentLook.ts'

// Parent-card illustration only. Student rewards and equipped companions are untouched.
const key = (parentId: string, childId: string) => `sagomungchi:family-avatar:v1:${parentId}:${childId}`
const memory = new Map<string, FriendId>()
export function familyAvatar(parentId: string, childId: string): FriendId {
  const id = key(parentId, childId)
  try { const stored = localStorage.getItem(id); if (isFriendId(stored)) return stored } catch { /* private storage */ }
  const cached = memory.get(id)
  if (cached) return cached
  const random = crypto.getRandomValues(new Uint32Array(1))[0]
  const choice = FRIENDS[random % FRIENDS.length].id
  saveFamilyAvatar(parentId, childId, choice, false)
  return choice
}
export function saveFamilyAvatar(parentId: string, childId: string, choice: FriendId, notify = true): boolean {
  memory.set(key(parentId, childId), choice)
  let saved = true
  try { localStorage.setItem(key(parentId, childId), choice) } catch { saved = false }
  if (notify) window.dispatchEvent(new Event('sagomungchi:family-avatar-changed'))
  return saved
}
