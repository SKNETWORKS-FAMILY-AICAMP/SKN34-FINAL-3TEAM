import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evidenceQuoteBlocks } from '../src/domain/reportEvidence.ts'

test('explicit numbered answer prompts separate without losing calculation or continuation text', () => {
  const blocks = evidenceQuoteBlocks('① 무엇을 구하나요?: 평균 병 수를 구해요.\n② 계산: 42÷3=14개예요.\n평균은 한 번에 해당하는 병 수예요.\n최종 답: 14')
  assert.deepEqual(blocks, [
    { label: '① 무엇을 구하나요?:', text: '평균 병 수를 구해요.' },
    { label: '② 계산:', text: '42÷3=14개예요.\n평균은 한 번에 해당하는 병 수예요.' },
    { label: '최종 답:', text: '14', final: true },
  ])
})
test('ordinary answers and incidental colons stay intact and are not inferred as questions', () => {
  for (const text of ['나는 9:45에 도서관에 갔다.\n다음에도 가고 싶다.', '① 참고: 내 생각\n전체 답변', '최종 답: 14', '']) {
    assert.deepEqual(evidenceQuoteBlocks(text), [{ text }])
  }
})
