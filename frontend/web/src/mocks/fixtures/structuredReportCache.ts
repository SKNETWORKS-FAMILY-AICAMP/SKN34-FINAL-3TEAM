export interface GemmaReportCache {
  model: string
  promptVersion: string
  items: { attemptId: string; answerVersion: number; sourceText: string; text: string }[]
}

/** Read an explicitly generated local artifact; never invoke a model from the browser. */
export async function loadStructuredReportCache(signal?: AbortSignal): Promise<GemmaReportCache | undefined> {
  const response = await fetch('/.taste-skill/structured-report-demo/gemma-explanations.json', { cache: 'no-store', signal })
  if (!response.ok) return undefined
  const value = await response.json()
  return typeof value?.model === 'string' && value.model.trim()
    && typeof value?.promptVersion === 'string' && value.promptVersion.trim() && Array.isArray(value?.items)
    ? value : undefined
}

export function matchingStructuredExplanation(cache: GemmaReportCache | undefined, sample: { attemptId: string; texts: string[] }): string | undefined {
  const item = cache?.items.find(item => item?.attemptId === sample.attemptId
    && item.answerVersion === sample.texts.length && item.sourceText === sample.texts.at(-1))
  return typeof item?.text === 'string' && item.text.trim() ? item.text : undefined
}
