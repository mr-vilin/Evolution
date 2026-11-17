"""成本执行策略：受理时校验并冻结，当前开关另由控制修订治理。"""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CostRunPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    max_attempts: int = Field(default=3, ge=1, le=5)
    deadline_seconds: int = Field(default=90, ge=30, le=300)
    run_deadline_seconds: int = Field(default=900, ge=60, le=86400)
    retry_base_seconds: int = Field(default=30, ge=5, le=300)
    retry_max_seconds: int = Field(default=300, ge=5, le=900)
    retry_jitter_seconds: int = Field(default=5, ge=0, le=30)
    lease_seconds: int = Field(default=120, ge=30, le=600)
    heartbeat_seconds: int = Field(default=20, ge=5, le=60)
    queue_deadline_seconds: int = Field(default=86400, ge=60, le=604800)
    queue_limit: int = Field(default=200, ge=1, le=500)
    max_rows: int = Field(default=10000, ge=1, le=10000)

    @model_validator(mode='after')
    def coherent_budgets(self):
        if self.heartbeat_seconds * 3 > self.lease_seconds:
            raise ValueError('心跳间隔不得超过租约的三分之一')
        if self.run_deadline_seconds < self.deadline_seconds:
            raise ValueError('轮次总预算不得小于单次采集预算')
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError('退避上限不得小于首次等待')
        return self


def effective_policy(value=None):
    return CostRunPolicy.model_validate(value or {}).model_dump()
