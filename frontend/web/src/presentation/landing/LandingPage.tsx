import { ArrowRight, BookOpen, MessageCircle, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { FRIENDS } from '../../domain/studentLook.ts'
import type { FriendId } from '../../domain/studentLook.ts'
import { landingEntryHref } from '../../domain/navigation.ts'
import { Companion } from '../student/world/Companion.tsx'
import { ForestRabbit } from './ForestRabbit.tsx'
import { UsageGuide } from './UsageGuide.tsx'
import './landing.css'

/** 장면마다 다른 친구를 고르되, 화면을 읽는 동안에는 조합을 유지한다. */
function chooseLandingFriends() {
  const friends = FRIENDS.filter((friend) => friend.id !== 'cotton').map((friend) => friend.id)
  for (let i = friends.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[friends[i], friends[j]] = [friends[j], friends[i]]
  }
  return friends.slice(0, 7)
}

const learningSteps = [
  { title: '문제를 읽고 내 생각 쓰기', body: '이번 주 이야기 속 문제를 읽고, 내가 생각한 답을 적어요.', label: '오늘의 미션', question: '우리 동네에 어떤 시설이 필요할까요?', answer: '우리 동네에는 도서관이 필요해요.', caption: '먼저, 내가 생각한 답을 적어요.' },
  { title: '질문에 답하며 이유 덧붙이기', body: '이어지는 질문에 답하면서 이유나 다른 생각을 덧붙여요.', label: '더 말해 보기', question: '도서관이 생기면 누구에게 어떤 도움이 될까요?', answer: '친구들이 함께 숙제할 수 있고, 어른들은 신문을 읽을 수 있어요.', caption: '누구에게 도움이 되는지 이유를 더했어요.' },
  { title: '처음 답과 고친 답 비교하기', body: '내 공책에서 두 답을 읽고, 어떤 점이 달라졌는지 살펴봐요.', label: '내 공책', question: '처음 생각에서 무엇이 더해졌나요?', answer: '도서관이 필요하다는 생각에, 누가 어떻게 이용할지 이유를 더했어요.', caption: '처음 답도, 고쳐 쓴 답도 공책에 남아요.' },
]

function NotebookLeaf({ step, side }: { step: number; side: 'left' | 'right' }) {
  const current = learningSteps[step]
  return side === 'left' ? <div className="lp-book-leaf lp-book-left">
      <span className="lp-book-running-head">생각을 담는 공책</span>
      <span className="lp-book-chapter">0{step + 1}</span>
      <span className="lp-example-label">{current.label}</span>
      <h3>{current.question}</h3>
      <span className="lp-book-page-number">{step * 2 + 1}</span>
    </div> : <div className="lp-book-leaf lp-book-right">
      <span className="lp-book-running-head">우리 동네에 필요한 시설</span>
      <div className="lp-book-writing"><span>{step === 0 ? '처음 남긴 답' : step === 1 ? '덧붙인 답' : '돌아보기'}</span><p>{current.answer}</p></div>
      <p className="lp-book-caption">{current.caption}</p>
      <span className="lp-book-page-number">{step * 2 + 2}</span>
    </div>
}

/** 작은 면을 연속 곡면으로 연결해 글씨와 종이가 함께 휘도록 한다. */
function CurvedLeaf({ step, side }: { step: number; side: 'left' | 'right' }) {
  return <div className="lp-curved-sheet">{Array.from({ length: 32 }, (_, i) => {
    const z = Math.sin(Math.PI * i / 32) * 12
    const dz = Math.sin(Math.PI * (i + 1) / 32) * 12 - z
    return <div className="lp-paper-band" key={i} style={{ '--band': i, '--depth': `${z}px`, '--rise': `${dz}px` } as CSSProperties}>
      <div className="lp-paper-band-content"><NotebookLeaf step={step} side={side} /></div>
    </div>
  })}</div>
}

function LearningStory({ friends }: { friends: FriendId[] }) {
  const [step, setStep] = useState(0)
  const [turn, setTurn] = useState<{ next: number; direction: 'next' | 'previous'; id: number } | null>(null)
  const turnId = useRef(0)
  const turning = turn !== null
  const changeStep = (next: number) => {
    if (turn || next === step) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setStep(next)
    } else {
      setTurn({ next, direction: next > step ? 'next' : 'previous', id: ++turnId.current })
    }
  }
  return <section className="lp-story lp-learning" id="learning" aria-labelledby="learning-title">
    <div className="lp-width lp-story-grid">
      <div className="lp-story-copy" data-landing-reveal>
        <p className="lp-section-label">아이의 하루</p>
        <h2 id="learning-title">왜 그렇게 생각했는지,<br /><span>한 번 더 써 봐요.</span></h2>
        <p className="lp-story-lead">답을 쓰면 AI가 질문을 건네요.<br />질문을 읽고 내 답에 이유를 더해 봐요.</p>
        <ol className="lp-journey" aria-label="학습 흐름 예시 선택">
          {learningSteps.map((item, index) => <li key={item.title}><button type="button" aria-pressed={step === index} disabled={turning} onClick={() => changeStep(index)} aria-controls="learning-example"><span className="lp-step-number">0{index + 1}</span><span><strong>{item.title}</strong><span>{item.body}</span></span></button></li>)}
        </ol>
        <Link className="lp-text-link" to={landingEntryHref('/student/login')}>학생으로 시작하기 <ArrowRight size={18} aria-hidden="true" /></Link>
      </div>
      <div className="lp-learning-scene" data-landing-reveal>
        <div className="lp-scene-friend lp-scene-friend-back" aria-hidden="true"><Companion friend={friends[0]} size={142} decorative /></div>
        <div className="lp-example-notebook">
          <div id="learning-example" className="lp-book-pages" aria-label="학습 흐름 예시 공책" aria-busy={turning} data-step={step}>
            <div className="lp-book-spread">
              <NotebookLeaf step={turn?.direction === 'previous' ? turn.next : step} side="left" />
              <NotebookLeaf step={turn?.direction === 'next' ? turn.next : step} side="right" />
            </div>
            {turn && <div key={turn.id} className="lp-turning-leaf" data-direction={turn.direction} aria-hidden="true" onAnimationEnd={event => {
              if (event.target !== event.currentTarget) return
              setStep(turn.next)
              setTurn(null)
            }}>
              <div className="lp-leaf-face lp-leaf-front"><CurvedLeaf step={step} side={turn.direction === 'next' ? 'right' : 'left'} /></div>
              <div className="lp-leaf-face lp-leaf-back"><CurvedLeaf step={turn.next} side={turn.direction === 'next' ? 'left' : 'right'} /></div>
            </div>}
          </div>
          <span className="lp-book-announcement" role="status">{learningSteps[step].title}</span>
        </div>
        <div className="lp-scene-friend lp-scene-friend-front" aria-hidden="true"><Companion friend={friends[1]} size={128} decorative /></div>
      </div>
    </div>
  </section>
}

function ParentStory({ friends }: { friends: FriendId[] }) {
  const [showQuestion, setShowQuestion] = useState(false)
  return <section className="lp-story lp-parent-story" id="family" aria-labelledby="family-title">
    <div className="lp-width">
      <header className="lp-parent-heading" data-landing-reveal>
        <div><p className="lp-section-label">학부모는 이렇게 봐요</p><h2 id="family-title">오늘 아이가 쓴 글,<br /><span>함께 읽어 보세요.</span></h2></div>
      </header>
      <div className="lp-parent-tabs" aria-label="학부모 기능 예시 선택">
        <button type="button" aria-pressed={!showQuestion} onClick={() => setShowQuestion(false)}><BookOpen size={16} aria-hidden="true" /> 기록 살펴보기</button>
        <button type="button" aria-pressed={showQuestion} onClick={() => setShowQuestion(true)}><MessageCircle size={16} aria-hidden="true" /> 기록에 질문하기</button>
      </div>
      <div className="lp-parent-canvas" data-focus={showQuestion ? 'question' : 'record'}>
        <span className="lp-canvas-orbit" aria-hidden="true" />
        <div className="lp-report-window">
          <div className="lp-family-paper-head"><span><BookOpen size={18} aria-hidden="true" /> 아이의 학습 기록</span><small>가상 기록 예시</small></div>
          <div className="lp-report-content">
              <span className="lp-example-label">우리 동네에 필요한 시설</span>
              <h3>아이가 더한 이유를<br />함께 읽어 보세요.</h3>
              <div className="lp-record-line"><span>처음 남긴 답</span><p>우리 동네에는 도서관이 필요해요.</p></div>
              <div className="lp-record-line lp-record-line-new"><span>덧붙인 답</span><p>친구들이 함께 숙제할 수 있고, 어른들은 신문을 읽을 수 있어요.</p></div>
          </div>
        </div>
        <div className="lp-chat-window">
          <div className="lp-chat-head"><span className="lp-chat-icon"><Sparkles size={19} aria-hidden="true" /></span><span>기록에 물어보기<small>아이의 답에서 이어지는 대화</small></span><span className="lp-chat-dots" aria-hidden="true">···</span></div>
          <p className="lp-parent-question">아이가 도서관이 필요하다고 생각한 이유는 뭔가요?</p>
          <div className="lp-record-reply"><span><Sparkles size={16} aria-hidden="true" /> 기록에서 살펴봤어요</span><p>친구들의 숙제와 어른들의 신문 읽기를 예로 들었어요. 도서관을 이용할 사람과 활동을 함께 떠올렸네요.</p><blockquote>“친구들이 함께 숙제할 수 있고, 어른들은 신문을 읽을 수 있어요.”</blockquote><small>근거 · 우리 동네에 필요한 시설 / 덧붙인 답</small></div>
        </div>
        <div className="lp-family-friends" aria-hidden="true"><span><Companion friend={friends[0]} size={112} decorative /></span><span><Companion friend={friends[1]} size={100} decorative /></span></div>
      </div>
        <ul className="lp-family-points">
          <li><BookOpen size={21} aria-hidden="true" /><span><strong>오늘 얼마나 했는지 확인해요</strong>일일·주간 리포트에서 학습 현황을 볼 수 있어요.</span></li>
          <li><MessageCircle size={21} aria-hidden="true" /><span><strong>궁금한 점은 기록에 질문</strong>공개된 답변을 근거로 AI와 대화해요.</span></li>
          <li><Sparkles size={21} aria-hidden="true" /><span><strong>공개 여부는 아이가 골라요</strong>글이 비공개여도 학습 수치는 확인할 수 있어요.</span></li>
        </ul>
        <div className="lp-parent-bottom"><Link className="lp-text-link" to={landingEntryHref('/login')}>학부모로 시작하기 <ArrowRight size={18} aria-hidden="true" /></Link></div>
    </div>
  </section>
}

type WorldTheme = 'forest' | 'space' | 'sea'

/** 배경 안의 장면을 CSS로 움직인다. 학생 화면의 기능과는 분리된 소개용 연출이다. */
function WorldAtmosphere({ theme, active }: { theme: WorldTheme; active: boolean }) {
  if (theme !== 'forest' && !active) return null
  if (theme === 'sea') return <div className="lp-atmosphere lp-ocean" aria-hidden="true">
    <span className="lp-sunray lp-sunray-one" /><span className="lp-sunray lp-sunray-two" /><span className="lp-sunray lp-sunray-three" /><span className="lp-water-glow" />
    {Array.from({ length: 7 }, (_, index) => <i className="lp-bubble" key={index} style={{ '--i': index } as CSSProperties} />)}
  </div>
  if (theme === 'space') return <div className="lp-atmosphere lp-cosmos" aria-hidden="true">
    {Array.from({ length: 18 }, (_, index) => <i className="lp-twinkle" key={index} style={{ '--i': index, left: `${8 + (index * 31) % 86}%`, top: `${8 + (index * 17) % 65}%` } as CSSProperties} />)}
    <span className="lp-meteor lp-meteor-one" /><span className="lp-meteor lp-meteor-two" /><span className="lp-meteor lp-meteor-three" />
  </div>
  return <div className="lp-atmosphere lp-meadow" aria-hidden="true">
    {active && <><span className="lp-meadow-light" />
      {Array.from({ length: 5 }, (_, index) => <i className="lp-pollen" key={index} style={{ '--i': index } as CSSProperties} />)}
    </>}
    <ForestRabbit active={active} />
  </div>
}

function MemoryGallery({ friends }: { friends: FriendId[] }) {
  const [hovered, setHovered] = useState<WorldTheme | null>(null)
  return <section className="lp-memory" id="memories" aria-labelledby="memories-title">
    <div className="lp-width">
      <header className="lp-memory-heading" data-landing-reveal>
        <div><p className="lp-section-label">공부가 끝나면</p><h2 id="memories-title">문제를 풀고 나면,<br /><span>꾸미는 재미도 있어요.</span></h2></div>
      </header>
      <div className="lp-gallery-stage" onPointerMove={(event) => {
        if (event.pointerType !== 'mouse' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
        const box = event.currentTarget.getBoundingClientRect()
        event.currentTarget.style.setProperty('--pointer-x', String(Math.max(-1, Math.min(1, (event.clientX - box.left) / box.width * 2 - 1))))
        event.currentTarget.style.setProperty('--pointer-y', String(Math.max(-1, Math.min(1, (event.clientY - box.top) / box.height * 2 - 1))))
      }} onPointerLeave={(event) => {
        event.currentTarget.style.setProperty('--pointer-x', '0')
        event.currentTarget.style.setProperty('--pointer-y', '0')
      }}>
        <div className="lp-gallery-orbit" aria-hidden="true" />
        {(['forest', 'space', 'sea'] as const).map((theme, index) => <figure className={`lp-memory-frame lp-memory-frame-${index + 1}`} key={theme}>
          <div className="lp-world" role="img" data-theme={theme} data-active={hovered === theme} aria-label={`${['생각 숲', '생각 우주', '생각 바다'][index]} 풍경`} onPointerEnter={(event) => { if (event.pointerType === 'mouse') setHovered(theme) }} onPointerLeave={() => setHovered(null)} onPointerCancel={() => setHovered(null)}>
            <img className="lp-world-background" src={`/student-assets/theme-card/${theme}.jpg`} alt="" loading="lazy" />
            <WorldAtmosphere theme={theme} active={hovered === theme} />
            <div className="lp-gallery-friend" aria-hidden="true"><Companion friend={friends[index]} size={142} decorative /></div>
          </div>
          <figcaption><span>0{index + 1}</span>{['생각 숲', '생각 우주', '생각 바다'][index]}<Sparkles size={17} aria-hidden="true" /></figcaption>
        </figure>)}
      </div>
      <div className="lp-play-gallery" aria-label="실제 학생 화면 예시">
        <figure className="lp-play-frame lp-play-room"><a className="lp-photo-mount" href="/landing/room-preview.jpg" target="_blank" rel="noreferrer" aria-label="미니룸 화면 크게 보기 (새 탭)"><img src="/landing/room-preview.jpg" alt="책상과 옷장, 추억 액자가 있는 실제 학생 미니룸 화면" loading="lazy" width="1098" height="445" /></a><figcaption><h3>내 방은 내가 꾸며요.</h3><p>옷을 갈아입고, 벽지와 가구도 바꿔 보세요.</p></figcaption></figure>
        <figure className="lp-play-frame lp-play-points"><a className="lp-photo-mount" href="/landing/points-preview.jpg" target="_blank" rel="noreferrer" aria-label="포인트 화면 크게 보기 (새 탭)"><img src="/landing/points-preview.jpg" alt="모은 포인트와 학습 활동별 적립 내역을 보여 주는 실제 학생 화면" loading="lazy" width="1110" height="445" /></a><figcaption><h3>학습하고 포인트 받기.</h3><p>미션과 돌아보기로 모은 포인트는 꾸미기에 쓸 수 있어요.</p></figcaption></figure>
        <figure className="lp-play-frame lp-play-album">
          <div className="lp-album-preview" aria-label="추억 앨범의 기념 액자 예시">
            {[
              { title: '잃어버린 지도 조각', image: 'past-map.jpg' },
              { title: '별빛 우체국', image: 'past-post.jpg' },
              { title: '숲속 발명 대회', image: 'past-forest.jpg' },
            ].map((item) => <div className="lp-album-card" key={item.image}>
              <span className="lp-album-picture"><img src={`/demo/album/${item.image}`} alt="" loading="lazy" /></span>
              <strong>{item.title}</strong>
            </div>)}
          </div>
          <figcaption><h3>다 푼 테마는 액자로 남겨요.</h3><p>한 주 다섯 문제를 모두 마치면 기념 액자를 받아요.</p></figcaption>
        </figure>
      </div>
    </div>
  </section>
}

/** #724: 공개 소개. 인증과 권한 검사는 기존 역할별 로그인 화면에서 처리한다. */
export function LandingPage() {
  const [guideOpen, setGuideOpen] = useState(false)
  const [friends] = useState(chooseLandingFriends)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) if (entry.isIntersecting) {
        (entry.target as HTMLElement).dataset.reveal = 'visible'
        observer.unobserve(entry.target)
      }
    }, { threshold: 0.1 })
    root.current?.querySelectorAll<HTMLElement>('[data-landing-reveal]').forEach((element) => {
      element.dataset.reveal = element.getBoundingClientRect().top > window.innerHeight ? 'pending' : 'visible'
      observer.observe(element)
    })
    return () => observer.disconnect()
  }, [])
  return <div className="landing-page" ref={root}>
    {guideOpen && <UsageGuide onClose={() => setGuideOpen(false)} />}
    <a className="lp-skip" href="#landing-main">본문으로 건너뛰기</a>
    <header className="lp-header lp-width">
      <Link className="lp-brand" to="/" aria-label="사고뭉치 홈"><img src="/brand-idea-transparent.png" alt="사고뭉치 · 생각을 잇는 배움" /></Link>
      <nav aria-label="서비스 소개 메뉴"><a href="#about" onClick={event => { event.preventDefault(); document.getElementById('about')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }) }}>서비스 소개</a><button className="lp-guide-trigger" type="button" aria-haspopup="dialog" onClick={() => setGuideOpen(true)}>이용 안내</button><Link className="lp-admin-entry" to={landingEntryHref('/admin/login')}>관리자 로그인 <ArrowRight size={14} aria-hidden="true" /></Link></nav>
    </header>
    <main id="landing-main">
      <div className="lp-hero-wrap"><section className="lp-hero lp-width" aria-labelledby="landing-title">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow">초등 3~6학년을 위한 사고력 학습</p>
          <h1 id="landing-title">내 생각을 쓰고,<br /><span>한 번 더 생각해요.</span></h1>
          <p className="lp-lead">이야기 속 문제를 풀고, 이어지는 질문에 답해요.<br />아이가 남긴 답은 공책과 학부모 리포트에서 볼 수 있어요.</p>
          <div className="lp-start-links">
            <Link className="lp-button lp-button-primary" to={landingEntryHref('/student/login')}>학생으로 시작하기 <ArrowRight size={18} aria-hidden="true" /></Link>
            <Link className="lp-button lp-button-secondary" to={landingEntryHref('/login')}>학부모로 시작하기 <ArrowRight size={18} aria-hidden="true" /></Link>
          </div>
          <p className="lp-signup">처음 오셨나요? <Link to={landingEntryHref('/signup')}>학부모 가입하기</Link></p>
        </div>
        <div className="lp-art" aria-hidden="true">
          <div className="lp-art-sun" />
          <span className="lp-art-spark"><Sparkles size={34} /></span>
          <div className="lp-mungchi"><Companion friend="cotton" size={310} decorative /></div>
          <div className="lp-thought-book"><span>오늘의 생각</span><strong>내 생각은<br />내 글로.</strong><span className="lp-book-line" /><span className="lp-book-line" /></div>
          <span className="lp-cloud lp-cloud-one" /><span className="lp-cloud lp-cloud-two" />
        </div>
      </section></div>
      <div className="lp-types" aria-label="다섯 가지 생각 활동"><ul className="lp-width"><li>분석하기</li><li>따져 보기</li><li>새로 만들기</li><li>문제 해결하기</li><li>돌아보기</li></ul></div>
      <section className="lp-about lp-width" id="about" aria-labelledby="about-title">
        <h2 id="about-title">아이의 생각은 어떻게 바뀌었을까요?</h2>
        <div className="lp-about-layout">
          <div className="lp-intro-art" aria-hidden="true">
            <div className="lp-intro-halo" />
            <span className="lp-intro-spark"><Sparkles size={36} /></span>
            <span className="lp-intro-note"><BookOpen size={31} /></span>
            <div className="lp-intro-character"><Companion friend="cotton" size={240} decorative /></div>
            <span className="lp-intro-shadow" />
          </div>
          <div className="lp-features">
          <article><span className="lp-feature-icon lp-icon-orange"><Sparkles size={27} aria-hidden="true" /></span><h3>생각하는 재미</h3><p>주간 이야기 속 미션을 풀어요.<br />모은 포인트로 뭉치와 내 방을 꾸며요.</p></article>
          <article><span className="lp-feature-icon lp-icon-blue"><BookOpen size={27} aria-hidden="true" /></span><h3>처음 답도, 고친 답도</h3><p>내 공책에서 두 답을 비교해요.<br />무엇을 덧붙였는지 다시 읽어 볼 수 있어요.</p></article>
          <article><span className="lp-feature-icon lp-icon-green"><MessageCircle size={27} aria-hidden="true" /></span><h3>아이의 기록에 질문하기</h3><p>학부모는 학습 현황과 리포트를 보고,<br />공개된 자녀 기록에 관해 AI에게 물어봐요.</p></article>
          </div>
        </div>
      </section>
      <LearningStory friends={friends.slice(0, 2)} />
      <ParentStory friends={friends.slice(2, 4)} />
      <MemoryGallery friends={friends.slice(4, 7)} />
      <section className="lp-onboarding" aria-labelledby="onboarding-title"><div className="lp-width lp-onboarding-inner"><div><h2 id="onboarding-title">첫 시작은 학부모와 함께.</h2><p>학부모 가입 <ArrowRight size={14} aria-hidden="true" /> 자녀·기기 등록 <ArrowRight size={14} aria-hidden="true" /> 학생 PIN 로그인</p></div><Link to={landingEntryHref('/signup')}>학부모 가입하기 <ArrowRight size={18} aria-hidden="true" /></Link></div></section>
    </main>
  </div>
}
