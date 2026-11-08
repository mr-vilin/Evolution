import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import type { Employee } from '../domain';
import { EmployeeDepartments } from './EmployeeDepartments';

it('前三个部门及剩余数量均显示为标签，悬停可查阅全部部门', async () => {
  const departments = Array.from({ length: 5 }, (_, index) => ({ id: 'd' + index, name: `部门${index}`, path: ['全公司', `部门${index}`] }));
  const employee = { id: 'u', name: '测试人员', departments: [...departments, departments[0]] } as Employee;
  render(<EmployeeDepartments employee={employee} />);
  const trigger = screen.getByRole('button', { name: '查看测试人员的全部部门，共 5 个' });
  expect(trigger.querySelectorAll('.org-membership-tag')).toHaveLength(3);
  expect(trigger.querySelector('.org-membership-more.ant-tag')?.textContent).toBe('+2');
  expect(screen.queryByText('部门4')).toBeNull();
  await userEvent.hover(trigger);
  expect(await screen.findByText('部门4')).toBeTruthy();
});
