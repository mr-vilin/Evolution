import type { ReactNode } from 'react';
import { App } from 'antd';
import { ThemeProvider } from '../theme/ThemeProvider';
import { AuthGate } from './AuthGate';
import { WorkspaceSettings } from './WorkspaceSettings';

export function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider>
    <App><AuthGate><WorkspaceSettings>{children}</WorkspaceSettings></AuthGate></App>
  </ThemeProvider>;
}
