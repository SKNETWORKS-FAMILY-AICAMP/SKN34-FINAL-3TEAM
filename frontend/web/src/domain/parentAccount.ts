/** #415 core 규칙과 같다: 영문·숫자 4~30자(서버가 소문자로 저장), 비밀번호 8~128자. */
export const LOGIN_ID_PATTERN = /^[A-Za-z0-9]{4,30}$/
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 128
export const PASSWORD_RECOVERY_NOTE =
  '비밀번호 찾기는 아직 제공하지 않습니다. 비밀번호를 잊었다면 로그인이 유지된 기기에서 문의하기를 이용하거나 새 아이디로 가입해 주세요.'

export function signupProblem(loginId: string, password: string, again: string, name: string): string | null {
  if (!LOGIN_ID_PATTERN.test(loginId.trim())) return '아이디는 영문과 숫자 4~30자로 입력해 주세요.'
  if (!name.trim() || name.trim().length > 80) return '이름을 입력해 주세요.'
  if (password.length < PASSWORD_MIN || password.length > PASSWORD_MAX) return `비밀번호는 ${PASSWORD_MIN}~${PASSWORD_MAX}자로 입력해 주세요.`
  if (password !== again) return '두 번 입력한 비밀번호가 다릅니다.'
  return null
}
