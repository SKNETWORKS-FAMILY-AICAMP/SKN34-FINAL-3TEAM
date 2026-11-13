import type { WordHelp } from '../../domain/learning.ts'

// 개발 목업 전용 낱말 물어보기(#599). 사전 원문이 아니라 직접 쓴 가상 뜻이며 실제 사전·AI를 부르지 않는다.
// 출처 표시는 화면 확인용이고, 실서버에서는 ai가 국립국어원 사전 응답만 쓴다(api-spec 4.2.7).
const WORDS: Record<string, { easy: string; example: string; definition: string }> = {
  까닭: { easy: '까닭은 어떤 일이 생긴 이유야.', example: '늦은 까닭을 말해 줬어.', definition: '(가상) 일이 생기게 된 원인이나 이유.' },
  화분: { easy: '화분은 꽃이나 풀을 심어 기르는 그릇이야.', example: '창가에 화분을 두었어.', definition: '(가상) 꽃이나 풀을 심어 가꾸는 그릇.' },
  도서관: { easy: '도서관은 책을 모아 두고 빌려 읽을 수 있는 곳이야.', example: '도서관에서 동화책을 빌렸어.', definition: '(가상) 책과 자료를 모아 두고 사람들이 보게 하는 곳.' },
  쓰임: { easy: '쓰임은 어떤 물건을 어디에 쓰는지를 말해.', example: '이 상자의 쓰임을 생각해 봤어.', definition: '(가상) 쓰이는 곳이나 쓰는 방법.' },
  경험: { easy: '경험은 내가 직접 해 보거나 겪어 본 일이야.', example: '캠핑은 재미있는 경험이었어.', definition: '(가상) 자기가 실제로 해 보거나 겪어 봄.' },
  분수: { easy: '분수는 똑같이 나눈 것 가운데 몇 개인지 나타내는 수야.', example: '피자 4조각 중 1조각은 4분의 1이야.', definition: '(가상) 전체를 똑같이 나눈 몫을 나타내는 수.' },
}
/** 목업 정답 낱말: 마무리 전에는 미룬다(실제로는 learning이 미션 정답 키·금지어를 보냄) */
const MOCK_ANSWER_WORDS = ['자석']
const OUT_OF_SCOPE = /(답\s*(을|좀)?\s*(알려|말해)|대신\s*(써|풀어)|몇\s*살|주소|전화)/

const reply = (state: WordHelp['state'], text: string, extra: Partial<WordHelp> = {}): WordHelp =>
  ({ state, headword: null, text, example: null, senses: [], ...extra })

export function mockWordHelp(question: string, open: boolean): WordHelp {
  if (OUT_OF_SCOPE.test(question))
    return reply('OUT_OF_SCOPE', '나는 문제 속 모르는 낱말의 뜻만 알려 줄 수 있어. 궁금한 낱말을 적어 줄래?')
  const word = question.trim().replace(/[?!.~\s]+$/g, '').replace(/(이|가)?\s*(뭐|무슨|무엇|뜻)\S*$/, '').trim()
    .replace(/(은|는|이|가|을|를|이란|란)$/, '')
  if (open && MOCK_ANSWER_WORDS.some(w => word.includes(w)))
    return reply('DEFERRED', '이 낱말은 문제의 답과 이어져 있어서 문제를 다 풀고 알려 줄게!')
  const entry = WORDS[word]
  if (!entry) return reply('NOT_FOUND', '사전에서 이 문장에 맞는 뜻을 찾지 못했어. 선생님이나 보호자께 물어보자.', { headword: word || null })
  return reply('EXPLAINED', entry.easy, { headword: word, example: entry.example, senses: [{ definition: entry.definition, source: '표준국어대사전' }] })
}
