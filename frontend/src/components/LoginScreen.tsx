import { type CSSProperties, useId } from 'react';
import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Spin, theme } from 'antd';
import { productName } from '../branding/product';
import { logoMarkPath } from '../branding/logo';
import type { ApiError } from '../services/http';
import './login-screen.css';

const orbitAngles = [-34, 28, 88];

function LoginArtwork() {
  const id = useId();
  const grid = `${id}-grid`;
  const glow = `${id}-glow`;
  const glass = `${id}-glass`;
  const edge = `${id}-edge`;

  return <svg className="login-artwork" viewBox="0 0 720 640" fill="none" aria-hidden="true">
    <defs>
      <pattern id={grid} width="32" height="32" patternUnits="userSpaceOnUse">
        <circle cx="8" cy="16" r="1" fill="var(--app-primary)" opacity=".24" />
      </pattern>
      <radialGradient id={glow}>
        <stop stopColor="var(--app-primary)" stopOpacity=".14" />
        <stop offset="1" stopColor="var(--app-primary)" stopOpacity="0" />
      </radialGradient>
      <linearGradient id={glass} x1="0" y1="0" x2="0" y2="1">
        <stop stopColor="var(--app-primary)" stopOpacity=".29" />
        <stop offset="1" stopColor="var(--app-primary)" stopOpacity=".06" />
      </linearGradient>
      <linearGradient id={edge} x1="0" y1="0" x2="1" y2="1">
        <stop stopColor="var(--login-art-edge)" />
        <stop offset="1" stopColor="var(--app-primary)" />
      </linearGradient>
    </defs>

    <circle cx="360" cy="320" r="300" fill={`url(#${glow})`} />
    <rect x="80" y="56" width="560" height="528" fill={`url(#${grid})`} />
    <g stroke="var(--app-primary)">
      <circle cx="360" cy="320" r="254" opacity=".2" strokeDasharray="1 6" />
      <circle cx="360" cy="320" r="224" opacity=".18" />
      <path d="M360 62v22m0 472v22M102 320h22m472 0h22" opacity=".55" />
    </g>

    {orbitAngles.map((angle) => <g key={angle} transform={`rotate(${angle} 360 320)`}>
      <ellipse cx="360" cy="320" rx="252" ry="102" stroke="var(--app-primary)" opacity=".35" />
      <ellipse className="login-orbit-trace" cx="360" cy="320" rx="252" ry="102"
        pathLength="100" stroke={`url(#${edge})`} strokeWidth="1.6" strokeLinecap="round"
        strokeDasharray="11 89" />
    </g>)}

    <g className="login-crystal" stroke={`url(#${edge})`} strokeLinejoin="round">
      <path d="m360 326 118 68-118 68-118-68Z" fill={`url(#${glass})`} opacity=".35" />
      <path d="m360 282 118 68-118 68-118-68Z" fill={`url(#${glass})`} opacity=".54" />
      <path d="m360 238 118 68-118 68-118-68Z" fill={`url(#${glass})`} opacity=".76" />
      <path d="m360 174 88 51-88 51-88-51Z" fill={`url(#${glass})`} strokeWidth="1.6" />
      <path d="m272 225 88 51v104l-88-51Z" fill={`url(#${glass})`} strokeWidth="1.6" />
      <path d="m360 276 88-51v104l-88 51Z" fill={`url(#${glass})`} strokeWidth="1.6" />
      <path d="m360 174 88 51v104l-88 51-88-51V225Z" strokeWidth="1.8" />
    </g>

    <circle cx="165" cy="190" r="3" fill="var(--app-primary)" opacity=".65" />
    <circle cx="360" cy="573" r="2.5" fill="var(--app-primary)" />
    <circle cx="568" cy="178" r="4" fill="var(--app-primary)" />
    <circle cx="568" cy="178" r="10" stroke="var(--app-primary)" opacity=".38" />
  </svg>;
}

export function LoginScreen({ error, onRecheck }: { error: ApiError | null; onRecheck: () => void }) {
  const { token } = theme.useToken();
  const loading = error === null;
  const needsLogin = error?.status === 401;
  const forbidden = error?.status === 403;
  const title = loading ? '正在验证管理员身份' : needsLogin ? '登录工作台' : forbidden ? '暂无管理权限' : '暂时无法进入工作台';

  return <main className="login-page" aria-labelledby="login-heading"
    style={{ '--login-ease-out': token.motionEaseOut } as CSSProperties}>
    <header className="login-brand">
      <svg className="login-mark" viewBox="0 0 1254 1254" aria-hidden="true">
        <path d={logoMarkPath} fill="currentColor" fillRule="evenodd" />
      </svg>
      <span>{productName}</span>
    </header>
    <div className="login-visual" aria-hidden="true"><LoginArtwork /></div>
    <section className="login-panel">
      <div className="login-content">
        <div className="login-rule" aria-hidden="true" />
        <div aria-live="polite">
          <h1 id="login-heading">{title}</h1>
          {needsLogin && <p>使用企业飞书身份登录，仅管理员白名单成员可访问。</p>}
          {!loading && !needsLogin && <p>{error.message}</p>}
        </div>
        {loading ? <div className="login-progress"><Spin /></div> : (
          <div className="login-actions">
            <Button className="login-primary" type="primary" href="/admin/auth/login"
              icon={<ArrowRightOutlined aria-hidden="true" />} iconPlacement="end">
              使用飞书登录
            </Button>
            <Button type="text" icon={<ReloadOutlined aria-hidden="true" />} onClick={onRecheck}>重新检查</Button>
          </div>
        )}
      </div>
    </section>
  </main>;
}
