"""叶片接口：维护叶片，覆盖提交检查、登记缺陷、更换叶片等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.blade import STATUS_ORDER as STATUSES
from app.services.blade import BladeService

router = APIRouter(prefix="/api/blade", tags=["叶片"])

service = BladeService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按叶片编号检索"),
    status: str | None = Query(default=None, description="待检查、完好、存在裂纹、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按叶片编号与状态过滤叶片列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status is not None and status.strip() and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"叶片状态「{status}」不在可选范围内")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/stats、/export 必须声明在 /{entry_id} 之前，否则会被当成叶片 ID 匹配，
# 访问 /api/blade/export 时会返回 422 而不是导出结果。
@router.get("/stats")
def blade_stats() -> dict[str, Any]:
    """叶片统计卡：数量全部按当期在管记录实时计算。"""
    return {"items": service.stats()}


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按叶片编号检索"),
    status: str | None = Query(default=None, description="待检查、完好、存在裂纹、已更换"),
) -> dict[str, Any]:
    """导出叶片清单：当前过滤条件下没有可导出的记录时，明确说明原因，而不是给出空文件。"""
    items, total = service.list_entries(keyword=keyword, status=status, page=1, size=10000)
    if total == 0:
        if keyword and keyword.strip():
            reason = f"没有叶片编号包含「{keyword.strip()}」的记录"
        elif status and status.strip():
            reason = f"当前没有「{status}」状态的叶片记录"
        else:
            reason = "叶片记录为空，请先登记叶片后再导出"
        raise HTTPException(status_code=409, detail=f"导出失败：{reason}")
    return {"module": "blade", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条叶片明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"叶片 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条叶片，缺字段或编号重复时说明原因；编号命中台账则沿用台账定级。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条叶片执行提交检查、登记缺陷、更换叶片；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
