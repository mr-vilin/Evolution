"""费用工作器安全结构化诊断：只保留类型、代码位置与白名单关联。"""
from datetime import datetime, timezone
import json
import logging
from pathlib import PurePath
import re
import traceback


def safe_exception(exc):
    """不访问异常正文、SQL参数、locals或源码行；异常链及调用帧均有界。"""
    chain=[];seen=set()
    while exc is not None and id(exc) not in seen and len(chain)<4:
        seen.add(id(exc))
        frames=[]
        for frame,line in traceback.walk_tb(exc.__traceback__):
            frames.append({'file':PurePath(frame.f_code.co_filename).name[:128],
                'function':re.sub(r'[^A-Za-z0-9_<>]','_',frame.f_code.co_name)[:96],'line':line})
        chain.append({'error_type':re.sub(r'[^A-Za-z0-9_]','_',type(exc).__name__)[:96],'frames':frames[-12:]})
        exc=exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return {'error_type':chain[0]['error_type'] if chain else 'UnknownError','exception_chain':chain}


class WorkerJsonFormatter(logging.Formatter):
    def format(self,record):
        # 已登记的腾讯事件文本仅含安全关联；第三方日志不复制任意正文。
        own=record.name.startswith('evolution.tencent.')
        message=record.getMessage() if own else ''
        event=message.split(' ',1)[0] if re.match(r'^tencent[.][a-zA-Z0-9_]+(?: |$)',message) else 'runtime.diagnostic'
        data={'timestamp':datetime.fromtimestamp(record.created,timezone.utc).isoformat(),
            'severity':record.levelname,'event_name':event,'logger':record.name}
        for key in ('job_id','attempt_id','config_id','generation','row_count'):
            match=re.search(r'(?:^| )'+key+r'=(\d+)(?: |$)',message)
            if match:data[key]=int(match.group(1))
        for key in ('reason_code','request_id'):
            match=re.search(r'(?:^| )'+key+r'=([A-Za-z0-9_.:-]{1,128})(?: |$)',message)
            if match:data[key]=match.group(1)
        if hasattr(record,'safe_diagnostic'):data['diagnostic']=record.safe_diagnostic
        return json.dumps(data,ensure_ascii=False,separators=(',',':'))


def configure_logging():
    handler=logging.StreamHandler();handler.setFormatter(WorkerJsonFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)


def log_exception(logger,event,exc,*,level=logging.ERROR,**context):
    fields=' '.join(key+'='+str(value) for key,value in context.items())
    logger.log(level,event+(' '+fields if fields else ''),extra={'safe_diagnostic':safe_exception(exc)})
