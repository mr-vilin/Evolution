import { type ReactNode, useEffect } from 'react';
import { AUTH_FAILURE_EVENT, setCsrfToken } from '../services/http';
import { useResource } from '../services/useResource';
import InitializationPage from '../pages/InitializationPage';
import { LoginScreen } from './LoginScreen';
import { AdminSessionContext, type AdminSession } from './AdminSessionContext';

export { useAdminSession } from './AdminSessionContext';

export function AuthGate({ children }: { children: ReactNode }) {
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

  if (session.data) {
    return <AdminSessionContext.Provider value={session.data}>
      {session.data.initialization_complete === true ? children : <InitializationPage />}
    </AdminSessionContext.Provider>;
  }

  return <LoginScreen error={session.loading ? null : session.error} onRecheck={session.reload} />;
}
