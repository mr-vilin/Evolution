import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import type { Employee } from '../domain';
import { EmployeeDepartments } from './EmployeeDepartments';

it('按主部门标识显示唯一名称及其他部门数量，悬停可查阅全部部门', async () => {
  const departments = Array.from({ length: 5 }, (_, index) => ({ id: 'd' + index, name: `部门${index}`, path: ['全公司', `部门${index}`] }));
  const employee = { id: 'u', name: '测试人员', primary_department_id: 'd3', departments: [...departments, departments[0]] } as Employee;
  render(<EmployeeDepartments employee={employee} />);
  const trigger = screen.getByRole('button', { name: '查看测试人员的全部部门，共 5 个' });
  expect(trigger.querySelectorAll('.org-membership-tag')).toHaveLength(1);
  expect(trigger.querySelector('.org-membership-tag')?.textContent).toBe('部门3');
  expect(trigger.querySelector('.org-membership-more.ant-tag')?.textContent).toBe('+4');
  expect(screen.queryByText('部门4')).toBeNull();
  await userEvent.hover(trigger);
  expect(await screen.findByText('部门4')).toBeTruthy();
});

it('主部门未采集时不把其他部门当作主部门，数量包含全部已知部门', () => {
  const employee = { id: 'u', name: '测试人员', primary_department_id: null,
    departments: [{ id: 'd1', name: '其他部门', path: ['其他部门'] }] } as Employee;
  render(<EmployeeDepartments employee={employee} />);
  const trigger = screen.getByRole('button', { name: '查看测试人员的全部部门，共 1 个' });
  expect(trigger.querySelector('.org-membership-tag')).toBeNull();
  expect(trigger.querySelector('.org-membership-more')?.textContent).toBe('+1');
});
