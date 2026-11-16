import { createContext, type ReactNode, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { colorVariables, createTheme, defaultColors, isHexColor, readColors, themeStorageKey, type ColorRole, type ThemeColors } from './colors';
import { themeLogoUrl } from '../branding/logo';

function loadColors() {
  try { return readColors(JSON.parse(localStorage.getItem(themeStorageKey) ?? 'null')); }
  catch { return { ...defaultColors }; }
}
const ThemeContext = createContext({ colors: defaultColors, savedColors: defaultColors, setColor: (_role: ColorRole, _value: string) => {}, saveColor: (_role: ColorRole): boolean => false, resetColor: (_role: ColorRole) => {}, reset: () => {}, storageError: '' });
export const useThemeColors = () => useContext(ThemeContext);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [savedColors, setSavedColors] = useState<ThemeColors>(loadColors);
  const [drafts, setDrafts] = useState<Partial<ThemeColors>>({});
  const colors = useMemo(() => ({ ...savedColors, ...drafts }), [savedColors, drafts]);
  const [storageError, setStorageError] = useState('');
  const config = useMemo(() => createTheme(colors), [colors]);
  const variables = useMemo(() => colorVariables(colors), [colors]);
  useEffect(() => {
    const icons = Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]'));
    const previous = icons.map(icon => icon.getAttribute('href'));
    for (const icon of icons) icon.href = themeLogoUrl(colors.primary);
    return () => icons.forEach((icon, index) => {
      const href = previous[index];
      if (href === null) icon.removeAttribute('href');
      else icon.setAttribute('href', href);
    });
  }, [colors.primary]);
  useLayoutEffect(() => {
    const style = document.documentElement.style;
    const previous = Object.fromEntries(Object.keys(variables).map(key => [key, style.getPropertyValue(key)]));
    for (const [key, value] of Object.entries(variables)) style.setProperty(key, value);
    return () => { for (const [key, value] of Object.entries(previous)) value ? style.setProperty(key, value) : style.removeProperty(key); };
  }, [variables]);
  useEffect(() => {
    const receive = (event: StorageEvent) => {
      if (event.key !== themeStorageKey && event.key !== null) return;
      try { setSavedColors(readColors(JSON.parse(event.newValue ?? 'null'))); }
      catch { setSavedColors({ ...defaultColors }); }
    };
    window.addEventListener('storage', receive);
    return () => window.removeEventListener('storage', receive);
  }, []);
  function persist(next: ThemeColors) {
    try {
      localStorage.setItem(themeStorageKey, JSON.stringify(next));
      setSavedColors(next);
      setStorageError('');
      return true;
    }
    catch { setStorageError('浏览器无法保存颜色，当前仅为预览；请重试勾选保存，或重置恢复原设置。'); return false; }
  }
  function resetColor(role: ColorRole) {
    setDrafts(previous => { const next = { ...previous }; delete next[role]; return next; });
    setStorageError('');
  }
  return <ThemeContext.Provider value={{ colors, savedColors, storageError, setColor: (role, value) => {
    if (Object.hasOwn(defaultColors, role) && isHexColor(value)) setDrafts(previous => ({ ...previous, [role]: value.toUpperCase() }));
  }, saveColor: role => {
    // 仅确认当前职责，其他色卡的预览不进入持久化快照。
    if (!persist({ ...savedColors, [role]: colors[role] })) return false;
    resetColor(role);
    return true;
  }, resetColor, reset: () => {
    setDrafts({ ...defaultColors });
    if (persist({ ...defaultColors })) setDrafts({});
  } }}>
    <ConfigProvider locale={zhCN} theme={config}>{children}</ConfigProvider>
  </ThemeContext.Provider>;
}
