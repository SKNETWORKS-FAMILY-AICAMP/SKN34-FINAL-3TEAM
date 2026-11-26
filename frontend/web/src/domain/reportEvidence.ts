export interface EvidenceQuoteBlock { label?: string; text: string; final?: boolean }

/** Format explicit numbered answer steps; never infer an original problem from a quote. */
export function evidenceQuoteBlocks(quote: string): EvidenceQuoteBlock[] {
  const lines = quote.split(/\r?\n/)
  const step = /^([①-⑩]\s*[^:：\r\n]{1,60}[:：])[ \t]*(.*)$/u
  if (lines.filter(line => step.test(line)).length < 2) return [{ text: quote }]
  const blocks: EvidenceQuoteBlock[] = []
  for (const line of lines) {
    const match = step.exec(line)
    const final = /^(최종 답\s*[:：])[ \t]*(.*)$/u.exec(line)
    if (match || final) {
      const [, label, text] = (match ?? final)!
      blocks.push({ label, text, ...(final ? { final: true } : {}) })
    } else if (blocks.length) blocks[blocks.length - 1].text += `\n${line}`
    else blocks.push({ text: line })
  }
  return blocks
}
