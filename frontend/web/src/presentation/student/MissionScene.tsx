import { useEffect, useState } from 'react'
import type { Mission } from '../../domain/classroom.ts'
export function MissionScene({ mission }: { mission: Mission }) {
  const [reduce, setReduce] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const changed = () => setReduce(media.matches)
    media.addEventListener('change', changed)
    return () => media.removeEventListener('change', changed)
  }, [])
  const uri = reduce ? mission.staticSceneUri : mission.sceneUri || mission.staticSceneUri
  if (uri && /^(https?:\/\/|\/[^/])/.test(uri))
    return (
      <figure className="ux-scene" data-motion={reduce ? 'static' : 'animated'}>
        <img src={uri} alt={mission.question} style={{ width: '100%', height: 'auto' }} />
        <figcaption>
          {reduce ? '정적 장면' : '미션 장면'}
          <label>
            <input
              type="checkbox"
              checked={reduce}
              onChange={(e) =>
                setReduce(
                  e.target.checked || window.matchMedia('(prefers-reduced-motion: reduce)').matches,
                )
              }
            />
            움직임 줄이기
          </label>
        </figcaption>
      </figure>
    )
  return (
    <figure
      className={`ux-scene ${reduce ? 'ux-scene-static' : ''}`}
      data-motion={reduce ? 'static' : 'animated'}
    >
      <SceneArt mission={mission} />
      <figcaption>
        <span>
          {reduce ? '정적 장면' : '움직이는 장면'} · 장면에서 확인한 것을 답에 남겨 주세요.
        </span>
        <label>
          <input
            type="checkbox"
            checked={reduce}
            onChange={(e) =>
              setReduce(
                e.target.checked || window.matchMedia('(prefers-reduced-motion: reduce)').matches,
              )
            }
          />
          움직임 줄이기
        </label>
      </figcaption>
    </figure>
  )
}

/** 미션 장면 그림만 (홈·미션 고르기 카드의 작은 장면에도 쓴다). */
export function SceneArt({ mission, decorative = false }: { mission: Pick<Mission, 'scene'>; decorative?: boolean }) {
  return (
  <svg
    viewBox="0 0 600 170"
    role={decorative ? undefined : 'img'}
    aria-hidden={decorative || undefined}
    aria-label={
      mission.scene === 'math'
        ? '사과가 든 두 상자. 질문을 읽고 수를 세어 보세요.'
        : mission.scene === 'science'
          ? '서로 다른 크기의 잎이 자란 두 화분. 관찰한 것을 비교해 보세요.'
          : '생각을 적는 펼친 공책과 연필.'
    }
  >
    <rect width="600" height="170" rx="12" fill="#f3f3df" />
    {mission.scene === 'math' ? (
      [0, 1].map((box) => (
        <g key={box} transform={`translate(${100 + box * 240},10)`}>
          <rect x="0" y="60" width="160" height="90" rx="10" fill="#cfb089" stroke="#a98a62" />
          {[0, 1, 2].map((i) => (
            <g
              className="ux-scene-piece"
              key={i}
              style={{ animationDelay: `${i * 0.15}s` }}
              transform={`translate(${24 + i * 48},57)`}
            >
              <ellipse rx="20" ry="23" fill="#b95e45" />
              <path d="M0 -22q-2 -15 12 -16" fill="none" stroke="#526d42" strokeWidth="4" />
              <ellipse cx="10" cy="-29" rx="9" ry="4" fill="#809769" />
            </g>
          ))}
        </g>
      ))
    ) : mission.scene === 'science' ? (
      [0, 1].map((i) => (
        <g key={i} transform={`translate(${180 + i * 240},130)`}>
          <path d="M-40 -20h80l-12 48h-56z" fill="#c69674" />
          <path d={`M0 -20v-${45 + i * 24}`} stroke="#718d58" strokeWidth="7" />
          <g className="ux-scene-piece">
            <ellipse
              cx="-18"
              cy={-48 - i * 22}
              rx={24 + i * 5}
              ry="12"
              transform={`rotate(25 -18 ${-48 - i * 22})`}
              fill="#9fb67f"
            />
            <ellipse
              cx="18"
              cy={-63 - i * 22}
              rx={24 + i * 5}
              ry="12"
              transform={`rotate(-25 18 ${-63 - i * 22})`}
              fill="#799a69"
            />
          </g>
        </g>
      ))
    ) : (
      <g>
        <path
          d="M130 36q75 -20 160 0v105q-80 -15 -160 0zm160 0q80 -20 165 0v105q-80 -15 -165 0"
          fill="#fffdf5"
          stroke="#abb59c"
          strokeWidth="3"
        />
        {[65, 85, 105].map((y) => (
          <path key={y} d={`M150 ${y}h120m40 0h120`} stroke="#dfe2cf" strokeWidth="2" />
        ))}
        <path className="ux-scene-piece" d="M470 40l-45 100 16 7 45-100z" fill="#8fa77e" />
      </g>
    )}
  </svg>
  )
}
