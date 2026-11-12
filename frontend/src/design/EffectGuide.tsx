import { useEffect, useState, type ReactNode } from 'react';
import { Badge, ConfigProvider, Drawer, theme, type DrawerProps, type GlobalToken } from 'antd';
import './effect-guide.css';

export function resolvedEffectToken(token: GlobalToken, name: string) {
  // 部分专用阴影由当前版本的组件内部消费，未列入公共 GlobalToken 类型。
  const value: unknown = Reflect.get(token, name);
  return typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : undefined;
}

export function EffectGuide({ children, className = '' }: { children: ReactNode; className?: string }) {
  const { token } = theme.useToken();
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const receive = () => setReducedMotion(preference.matches);
    receive();
    preference.addEventListener('change', receive);
    return () => preference.removeEventListener('change', receive);
  }, []);
  return <ConfigProvider theme={{
    token: { controlHeight: 32, borderRadius: 6, borderRadiusLG: 8, borderRadiusSM: 4, motion: token.motion && !reducedMotion },
    components: { Button: { fontWeight: 400 }, Card: { bodyPadding: 24 }, Popover: { borderRadiusLG: 4 }, Tabs: { itemSelectedColor: token.colorPrimary } },
  }}><div className={`panel effect-guide ${className}`}>{children}</div></ConfigProvider>;
}

export function EffectEntry({ id, title, tokens, usage, rule, code, children }: {
  id: string; title: string; tokens: string; usage: string; rule: string; code: string; children: ReactNode;
}) {
  const [showCode, setShowCode] = useState(false);
  const previewId = `${id}-preview`;
  return <article className="effect-entry" aria-labelledby={`${id}-title`}>
    <div className="effect-explanation"><h3 id={`${id}-title`}>{title}</h3><code>{tokens}</code><p>{usage}</p><p className="effect-reminder">{rule}</p></div>
    <div className="effect-example"><div className="effect-example-head"><span>{showCode ? '当前主题 · 样式规则' : '交互示例'}</span><button type="button" className="code-icon" aria-label={`${showCode ? '收起' : '查看'} ${title} 代码`} aria-expanded={showCode} aria-controls={previewId} onClick={() => setShowCode(!showCode)}>&lt;/&gt;</button></div>
      <div id={previewId} className={`effect-stage${showCode ? ' is-code' : ''}`}><div className="effect-live-example" hidden={showCode}>{children}</div>{showCode && <pre>{code}</pre>}</div>
    </div>
  </article>;
}

export function MemberPreviewDrawer({ open, onClose, placement = 'right', name = '林晓', title = '成员详情 · 示例' }: {
  open: boolean; onClose: () => void; placement?: DrawerProps['placement']; name?: string; title?: string;
}) {
  return <Drawer title={title} open={open} onClose={onClose} placement={placement} size={320} mask={{ blur: false, closable: true }} styles={{ section: { borderRadius: 8 }, body: { padding: 24 } }}>
    <div style={{ display: 'grid', gap: 16 }}><strong>{name}</strong><span>所属部门：研发部</span><span>职责：协同维护组织与成员资料</span><Badge status="success" text="在职" /><p style={{ margin: 0 }}>查看完成后可关闭抽屉，或按 Esc 返回原来的列表。</p></div>
  </Drawer>;
}
