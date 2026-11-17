/** Presentation only: never invent analysis or infer a missing improvement from prose. */
export interface ExplanationSection { title: string; body: string }
export type ExplanationBlock = { kind: 'paragraph'; text: string } | { kind: 'list'; ordered: boolean; items: string[] }

const titles = '상세 분석|보완할 지점|아이가 어려움을 겪은 지점|개선 방안|잘한 점|함께 이야기해 볼 점'
const heading = new RegExp(`^\\s*(?:#{1,6}\\s*)?(?:\\*\\*)?(?:\\[(${titles})\\]|(${titles}))(?:\\*\\*)?\\s*(?:[:：]\\s*(.*)|$)`)

function structuredSections(text: string): ExplanationSection[] | null {
  if (!text.trimStart().startsWith('{')) return null
  try {
    const value: unknown = JSON.parse(text)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const row = value as Record<string, unknown>
    // A different/malformed JSON payload must stay visible rather than losing fields.
    if (Object.keys(row).length !== 3 || typeof row.analysis !== 'string' || !row.analysis.trim() ||
      !(row.improvement_points === null || typeof row.improvement_points === 'string') ||
      !Array.isArray(row.next_steps) || !row.next_steps.length ||
      !row.next_steps.every(step => typeof step === 'string' && step.trim())) return null
    const sections = [{ title: '상세 분석', body: row.analysis }]
    if (typeof row.improvement_points === 'string' && row.improvement_points.trim()) {
      sections.push({ title: '보완할 지점', body: row.improvement_points })
    }
    sections.push({ title: '개선 방안', body: row.next_steps.map(step => `- ${step}`).join('\n') })
    return sections
  } catch { return null }
}

/** Supports the proposed JSON-in-text format and existing plain/labelled stored text. */
export function explanationSections(text: string): ExplanationSection[] {
  const structured = structuredSections(text)
  if (structured) return structured
  const sections: ExplanationSection[] = []
  let title = '상세 분석', lines: string[] = []
  const flush = () => {
    const body = lines.join('\n').trim()
    if (body) sections.push({ title, body })
    lines = []
  }
  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    const match = heading.exec(line)
    if (match) {
      flush()
      title = match[1] || match[2]
      if (match[3]) lines.push(match[3])
    } else lines.push(line)
  }
  flush()
  return sections.length ? sections : [{ title: '상세 분석', body: text }]
}

/** Keep paragraph boundaries; render explicit bullets/numbers as accessible lists. */
export function explanationBlocks(body: string): ExplanationBlock[] {
  const blocks: ExplanationBlock[] = []
  let paragraph: string[] = []
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
    paragraph = []
  }
  for (const line of body.split('\n')) {
    const bullet = /^\s*(?:([-*•])\s+|\d+[.)]\s+)(.+)$/.exec(line)
    if (bullet) {
      flush()
      const ordered = !bullet[1], previous = blocks.at(-1)
      if (previous?.kind === 'list' && previous.ordered === ordered) previous.items.push(bullet[2])
      else blocks.push({ kind: 'list', ordered, items: [bullet[2]] })
    } else if (!line.trim()) flush()
    else paragraph.push(line)
  }
  flush()
  return blocks
}
