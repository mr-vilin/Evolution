import { createContext, useContext } from 'react';

export interface AdminSession {
  open_id: string;
  csrf_token: string;
  initialization_complete: boolean;
  profile?: { name: string | null; avatar_url: string | null };
}

export const AdminSessionContext = createContext<AdminSession | null>(null);
export const useAdminSession = () => useContext(AdminSessionContext);
