import type { ClassroomGateway } from './gateway.ts'
import type { Feedback } from '../../domain/classroom.ts'
export async function pollFeedback(
  gateway: ClassroomGateway,
  id: string,
  answerId: string,
  onStatus: (f: Feedback) => void,
  signal: AbortSignal,
  delayMs = 1000,
) {
  for (let poll = 0; ; poll++) {
    signal.throwIfAborted()
    const result = await gateway.feedback(id, answerId, onStatus, signal)
    if (result.status !== 'RUNNING' && result.status !== 'PENDING') return result
    onStatus(result)
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer)
        reject(signal.reason)
      }
      const timer = setTimeout(
        () => {
          signal.removeEventListener('abort', abort)
          resolve()
        },
        Math.min(delayMs * 2 ** Math.min(poll, 3), 8000),
      )
      if (signal.aborted) abort()
      else signal.addEventListener('abort', abort, { once: true })
    })
  }
}
