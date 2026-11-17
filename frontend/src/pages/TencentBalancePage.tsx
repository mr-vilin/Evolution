import { Link, useParams } from '@umijs/max';
import { useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/PageHeader';
import { request } from '../services/http';

const queriedTime = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});

interface Balance {
  account_id: string; uin: string; alias: string; currency: string; unit: string; currency_source: string;
  queried_at: string; amounts: Record<string,string>;
}
const labels: Record<string,string> = {
  cash_account_balance:'现金账户余额', income_into_account_balance:'收益转入金额', present_account_balance:'赠送账户余额',
  freeze_amount:'冻结金额', owe_amount:'欠费金额', credit_amount:'信用额度', credit_balance:'信用账户可用余额',
  real_credit_balance:'信用账户真实可用余额', temp_credit:'临时信用额度',
};

export function TencentBalancePage() {
  const { id } = useParams<{id:string}>();
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<{id?:string; loading:boolean; data?:Balance; error?:string}>({loading:true});
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    let active = true;
    setState({id,loading:true});
    void request<Balance>(`/admin/api/tencent/accounts/${encodeURIComponent(id ?? '')}/balance`, {signal:controller.signal})
      .then(({data}) => {
        if (active && !controller.signal.aborted) setState(data.account_id === id
          ? {id,loading:false,data} : {id,loading:false,error:'账号已变化，请重新查询'});
      })
      .catch(error => {
        if (active) setState({id,loading:false,error:controller.signal.aborted ? '余额查询超时，请手动刷新重试' : error instanceof Error ? error.message : '余额查询失败，请重试'});
      }).finally(() => window.clearTimeout(timeout));
    return () => {active=false; controller.abort(); window.clearTimeout(timeout);};
  }, [id,refresh]);
  const data = state.id === id ? state.data : undefined;
  const loading = state.id !== id || state.loading;
  function reload() { setState({id,loading:true}); setRefresh(value => value+1); }
  return <PageHeader area="业务管理" title="实时余额" description="直接查询当前账号，金额单位为元。每次查询均核验账号归属，可手动刷新。" extra={<Space>
    <Link to="/tencent/accounts">返回腾讯云账号</Link>
    <Button aria-label="刷新余额" icon={<ReloadOutlined />} loading={loading} onClick={reload}>刷新余额</Button>
  </Space>}>
    {state.id === id && state.error && <Alert showIcon type="error" title="本次余额查询失败" description={state.error} style={{marginBottom:16}} />}
    {loading && <Card loading aria-label="正在查询余额" />}
    {data && <>
      <Card title="真实可用余额">
        <div className="secondary-text">{data.alias} · UIN {data.uin}</div>
        <div style={{fontSize:32,lineHeight:'40px',fontWeight:600,margin:'16px 0',overflowWrap:'anywhere'}}>{data.amounts.real_balance}</div>
        <div className="caption-text">人民币（CNY）· 元</div>
        <div className="secondary-text" style={{marginTop:16}}>本次查询时间（北京时间）：{queriedTime.format(new Date(data.queried_at))}</div>
      </Card>
      <Card className="block-gap" title="资金明细（人民币 CNY / 元）">
        <Descriptions column={{xs:1,md:2,xl:3}} items={Object.entries(labels).filter(([key]) => data.amounts[key] !== undefined).map(([key,label]) => ({
          key,label,children:<span style={{overflowWrap:'anywhere'}}>{data.amounts[key]}</span>,
        }))} />
        <p className="caption-text" style={{marginBottom:0}}>信用额度与信用账户余额按独立口径展示。币种依据国内站财务账本配置。</p>
      </Card>
    </>}
  </PageHeader>;
}

export default TencentBalancePage;
