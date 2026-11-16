import { createContext, type ReactNode, useContext, useEffect } from 'react';
import { Button, Result, Space, Spin } from 'antd';
import { AUTH_FAILURE_EVENT, setCsrfToken } from '../services/http';
import { useResource } from '../services/useResource';
import InitializationPage from '../pages/InitializationPage';
import { useThemeColors } from '../theme/ThemeProvider';
import { themeLogoUrl } from '../branding/logo';

interface AdminSession { open_id: string; csrf_token: string; initialization_complete: boolean }
const SessionContext = createContext<AdminSession | null>(null);
export const useAdminSession = () => useContext(SessionContext);

export function AuthGate({ children }: { children: ReactNode }) {
  const { colors } = useThemeColors();
  const session = useResource<AdminSession>('/admin/auth/session');
  useEffect(() => {
    setCsrfToken(session.data?.csrf_token ?? null);
    return () => setCsrfToken(null);
  }, [session.data]);
  useEffect(() => {
    const recheck = () => session.reload();
    window.addEventListener(AUTH_FAILURE_EVENT, recheck);
    return () => window.removeEventListener(AUTH_FAILURE_EVENT, recheck);
  }, [session.reload]);

  if (session.data) return <SessionContext.Provider value={session.data}>{session.data.initialization_complete === true ? children : <InitializationPage />}</SessionContext.Provider>;
  if (session.loading || !session.error) return <div style={{ padding: '25vh 24px', textAlign: 'center' }}><Spin size="large" /><p>正在验证管理员身份…</p></div>;
  const needsLogin = session.error.status === 401;
  const forbidden = session.error.status === 403;
  return <main className="login-page" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--app-canvas)', padding: 24 }}>
    <div style={{ width: 'min(560px, 100%)', background: 'var(--app-surface)', borderRadius: 12, padding: '24px 8px', border: '1px solid var(--app-line)' }}>
      <Result
        icon={needsLogin ? <img src={themeLogoUrl(colors.primary)} alt="EVOLUTION Logo" width={64} height={64} /> : undefined}
        status={needsLogin ? 'info' : forbidden ? '403' : 'warning'}
        title={needsLogin ? '组织服务' : forbidden ? '暂无管理权限' : '暂时无法进入工作台'}
        subTitle={needsLogin ? '使用企业飞书身份登录，仅管理员白名单成员可访问。' : session.error.message}
        extra={<Space wrap><Button type="primary" href="/admin/auth/login">使用飞书登录</Button><Button onClick={session.reload}>重新检查</Button></Space>}
      />
    </div>
  </main>;
}
