import {afterEach,expect,it,vi} from 'vitest';
import {AUTH_FAILURE_EVENT,requestFile} from './http';
afterEach(()=>vi.unstubAllGlobals());
it('CSV导出返回完整文件，失效会话发出统一通知且不下载错误正文',async()=>{
  const failure=vi.fn();window.addEventListener(AUTH_FAILURE_EVENT,failure);
  try {
    vi.stubGlobal('fetch',vi.fn(async()=>new Response('产品,费用\n全部,12.34567890',{headers:{'content-type':'text/csv; charset=utf-8'}})));
    expect(await (await requestFile('/admin/api/tencent/accounts/1/cost-export')).text()).toContain('12.34567890');
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({error:{code:'INITIALIZATION_INCOMPLETE',message:'需要初始化'}}),{status:409})));
    await expect(requestFile('/admin/api/tencent/accounts/1/cost-export')).rejects.toMatchObject({code:'INITIALIZATION_INCOMPLETE'});
    expect(failure).toHaveBeenCalledOnce();
    vi.stubGlobal('fetch',vi.fn(async()=>new Response('<html>登录</html>',{headers:{'content-type':'text/html'}})));
    await expect(requestFile('/admin/api/tencent/accounts/1/cost-export')).rejects.toMatchObject({code:'INVALID_RESPONSE'});
  } finally {window.removeEventListener(AUTH_FAILURE_EVENT,failure);}
});
