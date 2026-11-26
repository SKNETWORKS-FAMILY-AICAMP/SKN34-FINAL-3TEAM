import { Check, Plus, Settings, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { Child } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import { FRIENDS, friendById } from '../../domain/studentLook.ts'
import type { FriendId } from '../../domain/studentLook.ts'
import { useFamilyAvatar } from './useFamilyAvatar.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Companion } from '../student/world/Companion.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'
import { ProfileSettings } from './AccountForms.tsx'
import './family-profiles.css'

export function FamilyProfiles({ childItems, selectedId, onSelect, onAdd }: {
  childItems?: Child[]; selectedId?: string; onSelect: (child: Child) => void; onAdd: () => void
}) {
  const me = useParentQuery(['me'], () => parentApi.me())
  const [parentOpen, setParentOpen] = useState(false)
  return <section className="family-profiles" aria-label="우리 가족">
    <header className="family-heading"><h2>우리 가족</h2><span>{childItems ? `자녀 ${childItems.length} / 3명` : '자녀 확인 중'}</span></header>
    <QueryFeedback query={me} />
    {me.data && !me.error && <div className="family-members">
      <article className="family-member family-parent">
        <header><h3>{me.data.name || '보호자'}</h3><button className="family-settings-button" aria-label="보호자 정보 설정" onClick={() => setParentOpen(true)}><Settings size={19} aria-hidden="true" /></button></header>
        <div className="family-portrait family-parent-portrait" aria-hidden="true"><UserRound size={76} strokeWidth={1.2} /></div>
        <div className="family-member-info"><strong>보호자</strong><span>{me.data.email}</span></div>
      </article>
      {childItems?.map(child => <ChildCard key={`${me.data.userId}:${child.id}`} parentId={me.data.userId} child={child} selected={selectedId === child.id} onSelect={() => onSelect(child)} />)}
      {childItems && childItems.length < 3 && <button className="family-add" onClick={onAdd}>
        <span className="family-add-symbol"><Plus size={38} strokeWidth={1.5} aria-hidden="true" /></span><strong>자녀 추가 등록</strong><span>{3 - childItems.length}명 더 등록할 수 있어요</span>
      </button>}
    </div>}
    {childItems?.length === 3 && <p className="family-limit">자녀 3명이 모두 등록되어 있어요.</p>}
    {parentOpen && <Modal scrollIndicator title="보호자 정보 설정" onClose={() => setParentOpen(false)}><div className="family-profile-editor"><ProfileSettings section="parent" /></div></Modal>}
  </section>
}

function ChildCard({ parentId, child, selected, onSelect }: { parentId: string; child: Child; selected: boolean; onSelect: () => void }) {
  const [friend, saveFriend] = useFamilyAvatar(parentId, child.id)
  const [editing, setEditing] = useState(false)
  const portrait = friendById(friend)
  return <article className="family-member" data-selected={selected} aria-label={`${child.nickname} 자녀 카드`}>
    <header><h3>{child.nickname}</h3><button className="family-settings-button" aria-label={`${child.nickname} 프로필 설정`} onClick={() => setEditing(true)}><Settings size={19} aria-hidden="true" /></button></header>
    <div className="family-portrait" style={{ '--family-color': portrait.color } as CSSProperties}><Companion friend={friend} size={158} /></div>
    <div className="family-member-info"><strong>{gradeLabel(child.grade)}</strong><span>{child.birthYear}년생</span></div>
    <button className="family-select" aria-pressed={selected} onClick={onSelect}>{selected ? <><Check size={16} aria-hidden="true" />선택한 자녀</> : '이 자녀 선택'}</button>
    {editing && <Modal scrollIndicator title={`${child.nickname} 프로필 설정`} onClose={() => setEditing(false)}>
      <ChildProfileEditor child={child} friend={friend} onSave={saveFriend} />
    </Modal>}
  </article>
}

export function FamilyPortraitButton({ parentId, child }: { parentId: string; child: Child }) {
  const [friend, saveFriend] = useFamilyAvatar(parentId, child.id)
  const [open, setOpen] = useState(false)
  return <>
    <button className="family-portrait-button" aria-label={`${child.nickname} 뭉치 변경`} style={{ '--family-color': friendById(friend).color } as CSSProperties} onClick={() => setOpen(true)}>
      <Companion friend={friend} size={46} decorative /><Settings size={12} className="family-portrait-gear" aria-hidden="true" />
    </button>
    {open && <Modal scrollIndicator title={`${child.nickname} 뭉치 변경`} onClose={() => setOpen(false)}><ChildProfileEditor child={child} friend={friend} avatarOnly onSave={saveFriend} /></Modal>}
  </>
}

function ChildProfileEditor({ child, friend, onSave, avatarOnly = false }: { child: Child; friend: FriendId; onSave: (friend: FriendId) => boolean; avatarOnly?: boolean }) {
  const [section, setSection] = useState<'portrait' | 'info'>('portrait')
  const [infoVisited, setInfoVisited] = useState(false)
  const [choice, setChoice] = useState(friend)
  const [notice, setNotice] = useState('')
  return <div className="family-profile-editor">
    {!avatarOnly && <nav className="family-editor-tabs" aria-label="프로필 변경 항목"><button aria-pressed={section === 'portrait'} onClick={() => setSection('portrait')}>뭉치 변경</button><button aria-pressed={section === 'info'} onClick={() => { setInfoVisited(true); setSection('info') }}>자녀 정보</button></nav>}
    {section === 'portrait' ? <>
      <h3>함께할 뭉치를 골라 주세요</h3>
      <div className="family-avatar-options" role="group" aria-label="프로필 뭉치 선택">{FRIENDS.map(item => <button key={item.id} aria-pressed={choice === item.id} onClick={() => { setChoice(item.id); setNotice('') }}>
        <span style={{ '--family-color': item.color } as CSSProperties}><Companion friend={item.id} size={70} decorative /></span><strong>{item.name}</strong>{choice === item.id && <Check className="family-avatar-check" size={16} aria-hidden="true" />}
      </button>)}</div>
      <div className="family-editor-footer"><p>이 브라우저에서 사용하는 프로필 그림이에요.</p><button className="cj-primary" onClick={() => setNotice(onSave(choice) ? '프로필 뭉치를 저장했습니다.' : '현재 화면에 적용했습니다. 브라우저 저장 공간을 사용할 수 없어 다시 열면 유지되지 않을 수 있어요.')}>뭉치 저장</button></div>
      <p role="status">{notice}</p>
    </> : null}
    {infoVisited && <div hidden={section !== 'info'}><ProfileSettings key={child.id} section="child" child={child} /></div>}
  </div>
}
