// 案例专属适配层：只创建合成样本、返回演示结果，不依赖业务 HTTP 或真实身份。
export interface DemoItem { id: number; name: string; status: '进行中' | '已完成'; owner: string }
export function initialItems(): DemoItem[] {
  return Array.from({ length: 12 }, (_, index) => ({
    id: index + 1, name: `演示项目 ${index + 1}`, status: index % 3 === 0 ? '已完成' : '进行中', owner: '演示成员',
  }));
}
export function formReceipt(name: string) { return `演示提交成功：${name}`; }
export function loginReceipt(account: string) { return `演示登录成功：${account}。当前管理员会话保持有效。`; }
export function registrationReceipt(email: string) { return `演示注册完成：${email}。未创建真实账户。`; }
export function chatReply(text: string) { return `已收到“${text}”。这是本地模拟回复，你可以继续体验聊天交互。`; }
