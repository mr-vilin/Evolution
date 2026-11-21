import { createContext, type ReactNode, useContext, useEffect } from 'react';
import { AUTH_FAILURE_EVENT, setCsrfToken } from '../services/http';
import { useResource } from '../services/useResource';
import InitializationPage from '../pages/InitializationPage';
import { LoginScreen } from './LoginScreen';

interface AdminSession { open_id: string; csrf_token: string; initialization_complete: boolean }
const SessionContext = createContext<AdminSession | null>(null);
export const useAdminSession = () => useContext(SessionContext);

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
    return <SessionContext.Provider value={session.data}>
      {session.data.initialization_complete === true ? children : <InitializationPage />}
    </SessionContext.Provider>;
  }

  return <LoginScreen error={session.loading ? null : session.error} onRecheck={session.reload} />;
}
