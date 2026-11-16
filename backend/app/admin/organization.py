from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_admin_identity, get_runtime, require_admin_write
from app.directory.organization import OrganizationService
from app.stores.domain import UNSET, InvalidStoreChanges, StorePatch

router = APIRouter(prefix='/organization', tags=['organization'])


class DatasetVersion(BaseModel):
    dataset_epoch: str = Field(min_length=1, max_length=191)
    data_version: int = Field(ge=0)


@router.get('/summary')
def summary(dataset_epoch: str = Query(min_length=1), data_version: int = Query(ge=0), department_id: str = '0',
            identity=Depends(get_admin_identity), runtime=Depends(get_runtime)):
    data, meta = OrganizationService(runtime.sessions, runtime.reads).summary(
        dataset_epoch=dataset_epoch, data_version=data_version, department_id=department_id)
    return {'data': data, 'meta': meta}


@router.get('/employees')
def employees(department_id: str, include_descendants: bool = False, keyword: str = Query('', max_length=255),
              account_status: str = Query('all', pattern='^(all|activated|unactivated|frozen|unjoin|unknown)$'),
              view_status: str = Query('none', pattern='^(none|unactivated|unjoin|resigned)$'),
              limit: int = Query(20, ge=1, le=20), cursor: str | None = None,
              dataset_epoch: str = Query(min_length=1), data_version: int = Query(ge=0),
              identity=Depends(get_admin_identity), runtime=Depends(get_runtime)):
    data, meta = OrganizationService(runtime.sessions, runtime.reads).employees(
        department_id=department_id, include_descendants=include_descendants, keyword=keyword.strip(),
        account_status=account_status, view_status=view_status, limit=limit, cursor=cursor,
        dataset_epoch=dataset_epoch, data_version=data_version)
    return {'data': data, 'meta': meta}


class Selection(DatasetVersion):
    selected_ids: list[str] = Field(default_factory=list)
    toggle_id: str | None = Field(default=None, max_length=191)
    include_details: bool = False


class SiblingOrder(DatasetVersion):
    department_id: str = Field(min_length=1, max_length=191)
    parent_id: str = Field(min_length=1, max_length=191)
    anchor_id: str = Field(min_length=1, max_length=191)
    position: str = Field(pattern='^(before|after)$')


class OrganizationStoreChange(BaseModel):
    department_id: str = Field(min_length=1, max_length=191)
    is_store: bool = Field(strict=True)
    store_code: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class OrganizationStoreBatch(DatasetVersion):
    changes: list[OrganizationStoreChange] = Field(min_length=1)


@router.post('/stores')
def save_stores(body: OrganizationStoreBatch, authorization=Depends(require_admin_write), runtime=Depends(get_runtime)):
    changes = [StorePatch(
        change.department_id, change.is_store,
        change.store_code if 'store_code' in change.model_fields_set else UNSET,
        change.notes if 'notes' in change.model_fields_set else UNSET) for change in body.changes]
    try:
        data, meta = OrganizationService(runtime.sessions, runtime.reads).save_stores(
            changes, dataset_epoch=body.dataset_epoch, data_version=body.data_version,
            actor=f'admin:{authorization[0].open_id}')
    except InvalidStoreChanges as exc:
        raise HTTPException(422, {'code': 'INVALID_STORE_CHANGES', 'message': '门店修改无效',
                                  'fields': [error.__dict__ for error in exc.errors]})
    return {'data': data, 'meta': meta}


@router.post('/order')
def order(body: SiblingOrder, authorization=Depends(require_admin_write), runtime=Depends(get_runtime)):
    try:
        data, meta = OrganizationService(runtime.sessions, runtime.reads).order(
            **body.model_dump(), actor=f'admin:{authorization[0].open_id}')
    except ValueError as exc:
        raise HTTPException(422, {'code': str(exc), 'message': '仅可调整同父级部门的间隙顺序'})
    return {'data': data, 'meta': meta}


@router.post('/selection')
def selection(body: Selection, identity=Depends(get_admin_identity), runtime=Depends(get_runtime)):
    try:
        data, meta = OrganizationService(runtime.sessions, runtime.reads).selection(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, {'code': str(exc), 'message': '部门不可选，请刷新范围'})
    return {'data': data, 'meta': meta}


@router.get('/departments')
def departments(parent_id: str = '0', include_inactive: bool = False,
                limit: int = Query(100, ge=1, le=500), cursor: str | None = None,
                dataset_epoch: str | None = None, data_version: int | None = None,
                identity=Depends(get_admin_identity), runtime=Depends(get_runtime)):
    data, meta = OrganizationService(runtime.sessions, runtime.reads).departments(
        parent_id=parent_id, include_inactive=include_inactive, limit=limit, cursor=cursor,
        dataset_epoch=dataset_epoch, data_version=data_version)
    return {'data': data, 'meta': meta}


@router.get('/search')
def search(keyword: str = Query('', max_length=255), include_inactive: bool = False,
           dataset_epoch: str | None = None, data_version: int | None = None,
           identity=Depends(get_admin_identity), runtime=Depends(get_runtime)):
    data, meta = OrganizationService(runtime.sessions, runtime.reads).search(
        keyword=keyword, include_inactive=include_inactive,
        dataset_epoch=dataset_epoch, data_version=data_version)
    return {'data': data, 'meta': meta}
