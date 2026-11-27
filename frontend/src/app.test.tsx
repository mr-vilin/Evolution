import { renderHook } from '@testing-library/react';
import { getMenuData } from '@ant-design/pro-components';
import { getMatchMenu } from '@umijs/route-utils';
import { expect, it } from 'vitest';
import routes from '../config/routes';
import { layout } from './app';

it('业务菜单按组织、门店和腾讯云分组，详情页归属对应菜单', () => {
  const { result } = renderHook(() => layout({}));
  const { menuData } = getMenuData(routes, undefined, undefined, result.current.menuDataRender);
  const visiblePages = menuData.slice(0, 4).map(group => ({
    name: group.name,
    pages: group.children?.filter(page => !page.hideInMenu).map(page => page.name),
  }));
  expect(visiblePages).toEqual([
    { name: '组织管理', pages: ['组织架构', '组织同步', '配置中心', '变更记录'] },
    { name: '门店管理', pages: ['门店'] },
    { name: '腾讯云管理', pages: ['账号管理', '费用看板', '成本看板'] },
    { name: '系统管理', pages: ['管理设置', '系统信息'] },
  ]);
  for (const [path, parent, page] of [
    ['/employees/123', '/organization-management', '/organization'],
    ['/sync/jobs/123', '/organization-management', '/sync'],
    ['/organization-config', '/organization-management', '/organization-config'],
    ['/tencent/accounts/123/balance', '/tencent-management', '/tencent/accounts'],
  ]) {
    const selected = getMatchMenu(path, menuData, true).map(item => item.key);
    expect(selected).toEqual(expect.arrayContaining([parent, page]));
  }
});
