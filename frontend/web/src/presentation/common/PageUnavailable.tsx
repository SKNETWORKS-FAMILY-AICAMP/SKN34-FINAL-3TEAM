import { Link } from 'react-router'
import './page-unavailable.css'

/** Route and chunk failures must leave a way back even when the workspace cannot mount. */
export function PageUnavailable({ notFound = false }: { notFound?: boolean }) {
  return <main className="page-unavailable">
    <h1>{notFound ? '페이지를 찾을 수 없어요' : '화면을 불러오지 못했어요'}</h1>
    <p>{notFound ? '주소가 바뀌었거나 없는 페이지입니다. 주소를 확인하거나 처음 화면으로 이동해 주세요.' : '인터넷 연결을 확인한 뒤 다시 불러와 주세요. 계속 열리지 않으면 잠시 후 다시 이용해 주세요.'}</p>
    <div>
      {!notFound && <button type="button" onClick={() => window.location.reload()}>다시 불러오기</button>}
      <Link to="/">처음 화면으로</Link>
      <Link to="/parent/journal">학부모 화면으로</Link>
    </div>
  </main>
}
