export type PrimaryStoreStatus = 'resolved' | 'not_in_store' | 'unknown' | 'inconsistent' | 'inactive';
export type RecordStatus = 'active' | 'inactive';
export interface DepartmentPerson { user_id: string; name: string; avatar_url: string | null }
export interface DepartmentDetails extends Department {
  feishu_department_id: string; parent_name: string | null;
  leaders: Array<DepartmentPerson & { leader_type: 1 | 2 }>;
  chat_id: string | null; chat_name: string | null; chat_owner: DepartmentPerson | null;
  chat_status: 'available' | 'not_set' | 'unavailable' | 'not_applicable';
  detail_warnings: string[];
}
export interface Department { id: string; name: string; parent_id: string | null; path: string[]; status: RecordStatus; sync_quality?: string; is_root: boolean; leader_user_id?: string | null; leader_name?: string | null; is_store: boolean; store_code: string | null; notes: string | null; employee_count?: number; has_children?: boolean; sort_order?: number }
export type FieldReadability = 'readable' | 'not_collected' | 'unreadable';
export interface Employee { avatar_url?: string | null; leader_avatar_url?: string | null; join_date?: string | null; user_id?: string; email?: string | null; mobile?: string | null; field_readability?: Record<string, FieldReadability>; account_status?: Partial<Record<'is_frozen' | 'is_resigned' | 'is_activated' | 'is_exited' | 'is_unjoin', boolean | null>>; id: string; name: string; employee_no?: string | null; status: RecordStatus; sync_quality?: string; employee_type_id?: string | null; employee_type_name?: string | null; job_title?: string | null; leader_user_id?: string | null; leader_name?: string | null; permission_role_id?: string | null; permission_role_name?: string | null; store_attribute_id?: string | null; store_attribute_name?: string | null; department_ids: string[]; departments: Department[]; primary_department_id: string | null; stores: Array<{ id: string; name: string; is_primary: boolean; path: string[]; path_names: string[] }>; store_ids: string[]; primary_store_id: string | null; primary_store_status: PrimaryStoreStatus }
export interface Store extends Department { employee_count?: number; primary_employee_count?: number }
export interface SyncJobDetail { id?: number | string; object_type: string; object_id: string; object_name?: string | null; status: string; action?: string; changes?: ChangeLog[]; error_code?: string | null; error_message?: string | null; attempt?: number; started_at?: string | null; finished_at?: string | null; change_log_id?: number | null }
export interface SyncJob { id?: string; job_id?: string; type: string; status: string; stage?: string; phase?: string; root_department_id?: string | null; root_department_name?: string | null; trigger_label?: string; executor_name?: string; executor_avatar_url?: string | null; started_at?: string | null; finished_at?: string | null; error_detail?: string | null; processed_count?: number; progress_total?: number | null; progress_kind?: string; collection_progress?: { departments_processed?: number; employees_processed?: number; observed_at?: string }; attempt_count?: number; attempt?: number; execution_count?: number; retry_count?: number; create_time?: string; update_time?: string; error_code?: string | null; processed_department_count?: number; processed_employee_count?: number; total_count?: number | null; success_count?: number; failure_count?: number; details?: SyncJobDetail[]; [key: string]: unknown }
export interface ChangeLog { id: string | number; object_type?: string; object_id?: string; object_name?: string; action?: string; source?: string; actor?: string; actor_open_id?: string; job_id?: string; committed_at?: string; before?: unknown; after?: unknown }
export interface ApiClient { id?: string; client_id?: string; name: string; revoked_at?: string | null; active?: boolean; last_used_at?: string | null }
export interface PreviewToken { dataVersion: number; fingerprint: string }
export interface StoreChange { department_id: string; is_store: boolean; store_code?: string | null; notes?: string | null }

export function stableFingerprint(value: unknown) { return JSON.stringify(value); }
export function previewMatches(token: PreviewToken | null, dataVersion: number | undefined, fingerprint: string) { return Boolean(token && dataVersion !== undefined && token.dataVersion === dataVersion && token.fingerprint === fingerprint); }
export function primaryStoreLabel(status?: PrimaryStoreStatus) {
  return ({ resolved: '已解析', not_in_store: '不在门店', unknown: '暂无法判断', inconsistent: '数据不一致', inactive: '员工已失效' } as Record<string, string>)[status ?? ''] ?? '暂无法判断';
}
export function statusLabel(status?: RecordStatus) { return status === 'active' ? '有效' : status === 'inactive' ? '失效' : '未知'; }
export function isActive(value: { status?: RecordStatus }) { return value.status === 'active'; }
export function formatTime(value?: string | null) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(date); }
