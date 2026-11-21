import { theme, type ThemeConfig } from 'antd';

// 项目默认八色与 .codex/frontend-style.md 中已保存的配置保持一致。
export const defaultColors = {
  primary: '#38B8D2', auxiliary: '#6FA9F1', accent: '#FA8C16', canvas: '#F5F5F5',
  surface: '#FFFFFF', text: '#1F1F1F', muted: '#595959', line: '#F0F0F0',
};
export type ColorRole = keyof typeof defaultColors;
export type ThemeColors = typeof defaultColors;
export const themeStorageKey = 'evolution.design-colors.v1';
export const isHexColor = (value: unknown): value is string => typeof value === 'string' && /^#[\da-f]{6}$/i.test(value);

export function readColors(value: unknown): ThemeColors {
  const result = { ...defaultColors };
  if (value && typeof value === 'object') {
    for (const key of Object.keys(result) as ColorRole[]) {
      const color = (value as Record<string, unknown>)[key];
      if (isHexColor(color)) result[key] = color.toUpperCase();
    }
  }
  return result;
}

// 中性色由职责色混合，交互色阶交给 Ant Design defaultAlgorithm。
export function mixColor(base: string, foreground: string, amount: number) {
  const channels = [1, 3, 5].map(offset => Math.round(
    parseInt(base.slice(offset, offset + 2), 16) * (1 - amount) + parseInt(foreground.slice(offset, offset + 2), 16) * amount,
  ).toString(16).padStart(2, '0'));
  return `#${channels.join('')}`.toUpperCase();
}

export function createTheme(colors: ThemeColors): ThemeConfig {
  return {
    algorithm: theme.defaultAlgorithm,
    token: {
      colorPrimary: colors.primary, colorInfo: colors.primary, colorLink: colors.primary,
      colorBgBase: colors.surface, colorBgLayout: colors.canvas,
      colorBgContainer: colors.surface, colorBgElevated: colors.surface,
      colorTextBase: colors.text, colorText: colors.text, colorTextHeading: colors.text,
      colorTextSecondary: colors.muted, colorTextDescription: colors.muted,
      // 说明灰对应黑色 0.65：三级取 0.45，禁用与占位取 0.25；默认白底为 #8C8C8C / #BFBFBF。
      colorTextTertiary: mixColor(colors.surface, colors.muted, 0.45 / 0.65),
      colorTextQuaternary: mixColor(colors.surface, colors.muted, 0.25 / 0.65),
      colorTextDisabled: mixColor(colors.surface, colors.muted, 0.25 / 0.65),
      colorTextPlaceholder: mixColor(colors.surface, colors.muted, 0.25 / 0.65),
      colorBorder: mixColor(colors.line, colors.text, 0.11), colorBorderSecondary: colors.line,
      colorFillAlter: mixColor(colors.surface, colors.canvas, 0.5),
      colorFillQuaternary: mixColor(colors.surface, colors.canvas, 0.5),
      borderRadius: 6, fontWeightStrong: 600,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
    },
  };
}

export function colorVariables(colors: ThemeColors) {
  const token = theme.getDesignToken(createTheme(colors));
  const variables: Record<string, string> = {};
  for (const [name, value] of Object.entries(token)) {
    if (typeof value === 'string' && name.startsWith('color')) variables[`--${name.replace(/[A-Z]/g, match => `-${match.toLowerCase()}`)}`] = value;
  }
  for (const [name, value] of Object.entries(colors)) variables[`--app-${name}`] = value;
  variables['--app-auxiliary-bg'] = mixColor(colors.surface, colors.auxiliary, 0.1);
  variables['--app-accent-bg'] = mixColor(colors.surface, colors.accent, 0.1);
  variables['--app-auxiliary-border'] = mixColor(colors.surface, colors.auxiliary, 0.4);
  variables['--app-accent-border'] = mixColor(colors.surface, colors.accent, 0.4);
  return variables;
}
