import { useEffect, useRef } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { PlanComparison } from '../common/PlanComparison.tsx'

const sections = [
  { title: '처음 시작하기', items: [
    ['어떤 순서로 시작하나요?', '학부모 계정으로 가입한 뒤 이용 동의와 자녀 등록을 진행해 주세요. 자녀가 사용할 기기를 등록하고 PIN을 설정하면 학생 화면에서 학습을 시작할 수 있어요.'],
    ['학생은 어떻게 로그인하나요?', '학부모 화면의 기기·PIN에서 등록 코드를 발급해 주세요. 학생이 사용할 기기에서 QR 또는 등록 코드로 기기를 등록한 뒤, 자녀를 선택하고 PIN을 입력해요.'],
    ['PIN을 잊어버렸어요.', '학부모가 기기·PIN 화면에서 해당 자녀의 PIN을 다시 설정할 수 있어요. 학부모 로그인 비밀번호와 학생 PIN은 서로 달라요.'],
  ] },
  { title: '로그인과 기기 관리', items: [
    ['학부모 로그인과 학생 로그인은 다른가요?', '학부모는 가입할 때 사용한 Google 계정 또는 아이디·비밀번호로 로그인해요. 학생은 등록된 기기에서 자녀를 선택하고 PIN으로 로그인해요.'],
    ['새 기기에서 아이가 공부하려면 어떻게 하나요?', '새 기기도 학부모 화면의 기기·PIN에서 발급한 등록 코드로 등록해야 해요. 등록 뒤 자녀가 보이지 않는다면 해당 기기에 연결된 자녀를 확인해 주세요.'],
    ['사용하지 않는 기기는 어떻게 하나요?', '학부모 화면의 기기·PIN에서 등록 기기를 확인하고 사용하지 않는 기기의 등록을 해제해 주세요.'],
  ] },
  { title: '학생의 학습', items: [
    ['답을 제출하면 무엇을 하나요?', '학습 결과와 이어지는 질문을 확인하고, 이유를 덧붙이거나 답을 다시 생각해 봐요. 내 공책에서는 처음 답과 고친 답을 살펴볼 수 있어요.'],
    ['작성하던 글과 제출한 답은 다른가요?', '작성 중인 초안과 제출한 답변은 따로 관리돼요. 작성을 마쳤다면 제출 결과까지 확인해 주세요. 저장이나 제출에 실패했다는 안내가 나오면 다시 시도해 주세요.'],
    ['학습 결과나 질문이 이상하면 어떻게 하나요?', 'AI의 학습 안내에는 오류가 있을 수 있어요. 문의·오류 신고에서 문제가 있는 내용을 알려 주세요. 신고를 접수한다고 결과가 바로 바뀌는 것은 아니며, 처리 결과를 따로 확인할 수 있어요.'],
  ] },
  { title: '학부모의 기록 확인', items: [
    ['아이의 학습 기록은 어디서 보나요?', '학부모 화면에서 자녀와 조회 기간을 선택해 학습 현황과 리포트를 확인해 주세요. 아이가 쓴 답변 원문도 함께 살펴볼 수 있어요.'],
    ['아이의 답변 원문을 볼 수 있나요?', '네. 자녀를 등록할 때 법정대리인 동의서에 동의하시면 답변 원문과 리포트, 추억 그림책을 이용할 수 있어요. 아이에게는 처음 둘러보기에서 학부모님이 답을 보실 수 있다고 알려 줘요. 동의서가 새로 바뀌면 다시 동의하신 뒤 이용할 수 있어요.'],
    ['기록에 물어보기는 어떤 기능인가요?', '선택한 자녀와 기간의 학습 기록을 바탕으로 AI에게 질문하는 기능이에요. 프리미엄 이용권이 필요하며, AI의 설명은 아이를 이해하기 위한 참고로 활용해 주세요.'],
    ['추억 그림책은 어떤 기능인가요?', '아이가 한 주 테마를 모두 마쳐 받은 기념 액자마다, 그 주의 그림과 아이의 답을 엮은 그림책(PDF)을 리포트 화면에서 발급할 수 있어요. 프리미엄 이용권이 필요하고, 자녀당 하루 3권까지 발급할 수 있어요. 만든 파일은 30일 동안 받을 수 있어요.'],
  ] },
  { title: '이용권·결제', items: [
    ['이용권은 어디서 확인하나요?', '학부모 화면의 이용권·결제에서 현재 이용권과 제공 기능을 확인할 수 있어요. 가입이나 결제 전에는 화면에 안내된 가격과 이용 조건을 확인해 주세요.'],
    ['결제하면 자동으로 매달 결제되나요?', '1개월 이용권 구매와 자동 갱신 등록은 별도예요. 결제 화면에서 이용 기간과 자동 갱신 동의 여부를 확인해 주세요.'],
  ] },
  { title: '포인트·방 꾸미기', items: [
    ['모은 포인트와 내역은 어디서 보나요?', '학생 화면의 내 포인트에서 잔액과 적립·사용 내역을 볼 수 있어요. 미션과 돌아보기 등 활동별 적립 기준도 이 화면에서 확인해 주세요.'],
    ['포인트로 무엇을 할 수 있나요?', '꾸미기 아이템을 구매해 옷을 바꾸거나 미니룸의 벽지와 가구를 꾸밀 수 있어요. 구매 전 필요한 포인트를 확인해 주세요.'],
  ] },
  { title: '친구 생각·공유', items: [
    ['친구들의 답은 언제 볼 수 있나요?', '내가 마무리한 미션의 친구 생각을 볼 수 있어요. 같은 미션을 푼 친구들의 답을 읽고 정해진 반응을 남길 수 있어요.'],
    ['내 답이 친구들에게 자동으로 공개되나요?', '보호자의 커뮤니티 이용 동의 후 자녀가 직접 친구 공개를 켜야 해요. 학부모님이 답변을 보시는 것과 친구 공개는 별개예요.'],
  ] },
  { title: '계정과 개인정보' , items: [
    ['동의를 철회하면 계정도 삭제되나요?', '동의 철회와 계정 삭제는 다른 절차예요. 공개·동의 설정에서 동의를 관리할 수 있으며, 필수 동의를 철회하면 이용이 제한될 수 있어요. 자녀 삭제나 회원 탈퇴는 계정 관리에서 별도로 진행해 주세요.'],
    ['자녀 연결 해제와 자녀 삭제는 무엇이 다른가요?', '연결 해제와 데이터 삭제는 서로 다른 작업이에요. 학부모 화면의 계정 관리에서 대상과 영향을 확인한 뒤 본인 확인을 거쳐 진행해 주세요. 다른 학부모에게 자녀 관리를 넘길 때는 자녀 이관 기능을 이용해 주세요.'],
    ['아이 답변이 AI 학습에 쓰이나요?', '학습 피드백과 리포트를 만드는 외부 AI의 학습에는 쓰이지 않아요. 다만 걸러내기 판단이 애매했던 답변과 신고된 공유 글은 이름 없이 글만 사고뭉치 서버 안에서 부적절한 표현을 걸러내는 기능을 고치는 데 쓰여요. 자세한 내용은 위의 개인정보 처리방침에서 확인할 수 있어요.'],
    ['개인정보는 어떻게 처리하나요?', '수집 항목, 이용 목적, 보관과 삭제 기준은 위의 개인정보 문서에서 확인할 수 있어요. 문의나 오류 신고에는 비밀번호·카드 정보 등 민감한 정보를 적지 말아 주세요.'],
  ] },

]

export function UsageGuide({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const documents = useParentQuery(['consents'], signal => parentApi.documents(signal))
  useEffect(() => {
    const element = dialog.current!
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    element.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      element.close()
      document.body.style.overflow = overflow
      previous?.focus()
    }
  }, [])
  return <dialog ref={dialog} className="lp-guide" aria-labelledby="usage-guide-title" onCancel={event => { event.preventDefault(); onClose() }}>
    <header className="lp-guide-header">
      <div><span>사고뭉치</span><h2 id="usage-guide-title">이용 안내</h2></div>
      <button className="lp-guide-close" type="button" aria-label="이용 안내 닫기" onClick={onClose} autoFocus><X size={24} aria-hidden="true" /></button>
    </header>
    <div className="lp-guide-content">
      <section className="lp-guide-policies" aria-labelledby="usage-policies-title">
        <h3 id="usage-policies-title">약관 및 개인정보</h3>
        {documents.isPending && <p role="status">약관을 불러오고 있어요.</p>}
        {documents.isError && <div role="alert"><p>약관을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p><button type="button" onClick={() => { void documents.refetch() }}>다시 불러오기</button></div>}
        {documents.data?.items.length === 0 && <p>현재 등록된 약관이 없습니다.</p>}
        {documents.data?.items.map(item => <details className="lp-guide-item" key={item.documentId}>
          <summary><span>{item.title}<small>버전 {item.version} · {item.required ? '필수' : '선택'}</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
          {item.kind === 'TERMS' ? <div className="lp-terms-content">
            <p className="lp-terms-note">사고뭉치 이용 시 알아둘 내용입니다. 동의 대상인 문서 원문은 아래에서 확인할 수 있어요.</p>
            <dl className="lp-terms-overview">
              <dt>학생과 학부모의 이용</dt><dd>학생은 미션에 답하고 이어지는 질문과 돌아보기를 통해 생각을 정리해요. 학부모는 연결된 자녀의 학습 기록과 리포트를 확인해요.</dd>
              <dt>AI 질문과 설명</dt><dd>AI가 제공하는 질문·설명에는 오류가 있을 수 있어요. 이상한 내용은 문의·오류 신고에서 알려 주세요.</dd>
              <dt>답변과 표현 걸러내기 개선</dt><dd>걸러내기 판단이 애매했던 답변과 신고된 공유 글은 이름 없이 글만 부적절한 표현을 걸러내는 기능을 고치는 데 쓰여요. 학습은 사고뭉치 서버 안에서만 하고, 끝나면 학습용 사본을 지워요.</dd>
              <dt>답변 열람과 친구 공유</dt><dd>학부모님은 법정대리인 동의로 자녀의 답변 원문을 볼 수 있어요. 친구 공개는 따로이며, 보호자 동의 후 자녀가 직접 켜요.</dd>
              <dt>이용권과 결제</dt><dd>제공 기능과 이용 기간은 이용권·결제 화면에서 확인해 주세요. 1개월 이용권 구매와 자동 갱신 등록은 별도예요.</dd>
              <dt>계정 관리와 데이터 삭제</dt><dd>동의 철회, 자녀 연결 해제, 자녀 삭제, 회원 탈퇴는 서로 다른 절차예요. 진행 전에 화면에 표시된 대상과 영향을 확인해 주세요.</dd>
            </dl>
            <details className="lp-terms-original"><summary>동의 문서 원문 보기<ChevronDown size={18} aria-hidden="true" /></summary><p className="lp-guide-policy-text">{item.content}</p></details>
          </div> : <p className="lp-guide-policy-text">{item.content}</p>}
        </details>)}
      </section>
      <section className="lp-guide-basics" aria-labelledby="usage-basics-title">
        <h3 id="usage-basics-title">이용 길잡이</h3>
        <details className="lp-guide-category">
          <summary><span>처음 이용하기 전 준비</span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="lp-guide-article"><p className="lp-guide-location">학부모 가입 → 자녀 등록 → 기기·PIN</p><ol className="lp-guide-checklist">
            <li><strong>학부모 계정 준비</strong><span>가입과 이용 동의를 마치고 학습할 자녀를 등록해 주세요.</span></li>
            <li><strong>학습 기기 연결</strong><span>학부모 화면의 기기·PIN에서 등록 코드를 발급하고, 아이가 쓸 기기에서 등록해 주세요.</span></li>
            <li><strong>학생으로 시작</strong><span>등록된 자녀를 선택하고 PIN을 입력하면 학습을 시작할 수 있어요.</span></li>
          </ol></div>
        </details>
        <details className="lp-guide-category">
          <summary><span>무료·프리미엄 비교</span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="lp-guide-article"><PlanComparison heading="h3" /></div>
        </details>
        <details className="lp-guide-category">
          <summary><span>안전하게 이용하기</span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="lp-guide-article"><ul className="lp-guide-checklist">
            <li><strong>계정과 PIN은 따로 관리해요</strong><span>비밀번호와 학생 PIN은 다른 사람에게 알려 주지 마세요. 함께 쓰는 기기에서는 이용 후 로그아웃해 주세요.</span></li>
            <li><strong>공개 범위를 확인해요</strong><span>자녀의 답변은 학부모님께 보여요. 친구에게 답을 공개하는 것은 따로이며, 보호자 동의 후 자녀가 직접 켜요.</span></li>
            <li><strong>AI 안내도 함께 살펴봐요</strong><span>AI의 질문과 설명에는 오류가 있을 수 있어요. 이상한 내용은 문의·오류 신고로 알려 주세요.</span></li>
          </ul></div>
        </details>
        <details className="lp-guide-category">
          <summary><span>문의·오류 신고 안내</span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="lp-guide-article"><ul className="lp-guide-checklist">
            <li><strong>접수와 답변 확인</strong><span>로그인 후 문의·오류 신고에서 접수하고, 내 접수 내역에서 처리 상태와 답변을 확인해 주세요.</span></li>
            <li><strong>이 내용을 알려 주세요</strong><span>문제가 발생한 화면, 눌렀던 버튼, 발생 시각과 오류 문구를 적어 주시면 확인에 도움이 돼요. 비밀번호·PIN·카드 정보는 적지 마세요.</span></li>
            <li><strong>점검 안내 확인</strong><span>접속이나 저장이 계속 안 된다면 로그인 후 공지·점검 메뉴도 확인해 주세요.</span></li>
          </ul></div>
        </details>
      </section>
      <div className="lp-guide-faq">
      <h3>자주 묻는 질문</h3>
      {sections.map(section => <details className="lp-guide-category lp-guide-section" key={section.title}>
        <summary><span>{section.title}</span><ChevronDown size={18} aria-hidden="true" /></summary>
        <div className="lp-guide-questions">
        {section.items.map(([question, answer]) => <details className="lp-guide-item" key={question}>
          <summary><span>{question}</span><ChevronDown size={18} aria-hidden="true" /></summary><div className="lp-guide-answer"><p>{answer}</p></div>
        </details>)}
        </div>
      </details>)}
      </div>
    </div>
  </dialog>
}
