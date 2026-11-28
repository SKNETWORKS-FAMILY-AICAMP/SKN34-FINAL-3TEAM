import test from 'node:test'
import assert from 'node:assert/strict'
import { revealText } from '../src/domain/classroom.ts'

// #1093 마무리 예시 답: 칸을 " / "로 이어 붙인 글을 칸마다 한 줄로(내 답과 같은 방식). 앞뒤 빈칸 없는 빗금은 그대로
test('앞뒤 빈칸 있는 " / "만 줄바꿈으로 바꾼다', () => {
  assert.equal(revealText('주장: 써도 돼요. / 까닭 1: 연락 / 반대 의견에 답하기: 아니에요'), '주장: 써도 돼요.\n까닭 1: 연락\n반대 의견에 답하기: 아니에요')
  assert.equal(revealText('1/2와 3 /4, 5/ 6은 그대로'), '1/2와 3 /4, 5/ 6은 그대로')
  assert.equal(revealText('빗금 없는 글'), '빗금 없는 글')
})
