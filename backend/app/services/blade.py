"""叶片业务规则：状态流转、字段校验、筛选口径与台账定级都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "blade"
REQUIRED_FIELDS = ["叶片编号", "所属机组", "叶片长度"]
OPTIONAL_FIELDS = ["制造厂商"]
STATUS_ORDER = ["待检查", "完好", "存在裂纹", "已更换"]
ACTION_RULES = {"提交检查": "完好", "登记缺陷": "存在裂纹", "更换叶片": "已更换"}

# 统计卡片的口径固定在这里，前端只负责展示，避免各算各的残留旧值。
STAT_LABELS = ["待检查叶片", "存在裂纹叶片", "本月更换数"]


class BladeService:
    def __init__(self) -> None:
        # 叶片台账：叶片编号 -> 最近一次定级等档案信息。
        # 检查记录可以清空，台账不随记录删除；重新登记时编号定级以台账这一份为准。
        self._ledger: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            self._remember_ledger(row)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        if status is not None and status not in STATUS_ORDER:
            raise ValueError(f"叶片状态只支持：{'、'.join(STATUS_ORDER)}")
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("叶片编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._present(row) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        """登记一条叶片。

        返回 (记录, 缺失字段, 说明)：编号在当前记录里已存在时拦下；
        编号在台账里有档案（例如检查记录清空后重新登记）时，定级以台账为准保留。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        code = str(values["叶片编号"]).strip()
        rows = store.rows(MODULE)
        if any(str(row.get("叶片编号", "")).strip() == code for row in rows):
            return None, [], f"叶片编号 {code} 已在当前检查记录中，无需重复登记"

        archived = self._ledger.get(code)
        grade = str(archived["grade"]) if archived else STATUS_ORDER[0]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = str(values[field]).strip()
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = str(values[field]).strip()
        entry["上次检查日"] = ""
        entry["裂纹数量"] = 0
        entry["雷击次数"] = 0
        entry["status"] = grade
        entry["叶片状态"] = grade
        entry["pending"] = grade != STATUS_ORDER[-1]
        entry["abnormal"] = grade == "存在裂纹"
        rows.append(entry)
        self._remember_ledger(entry)
        if archived and grade != STATUS_ORDER[0]:
            message = f"叶片已重新登记，编号 {code} 的台账定级「{grade}」已保留"
        else:
            message = "叶片已登记"
        return entry, [], message

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"叶片 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于叶片可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["叶片状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = target == "存在裂纹"
        if action == "更换叶片":
            entry["更换日期"] = date.today().isoformat()
        self._remember_ledger(entry)
        return self._present(entry), f"叶片已{action}"

    def clear_entries(self) -> int:
        """清空检查记录，但台账定级保留，供重新登记时沿用。"""
        rows = store.rows(MODULE)
        count = len(rows)
        rows.clear()
        return count

    def stats(self) -> list[dict[str, Any]]:
        """按当前记录实时统计，记录清空或重新登记后立即反映，不残留上一批的值。"""
        rows = store.rows(MODULE)
        month_prefix = date.today().strftime("%Y-%m")
        values = [
            sum(1 for row in rows if row.get("status") == "待检查"),
            sum(1 for row in rows if row.get("status") == "存在裂纹"),
            sum(1 for row in rows if str(row.get("更换日期") or "").startswith(month_prefix)),
        ]
        return [{"label": label, "value": value} for label, value in zip(STAT_LABELS, values)]

    def _remember_ledger(self, row: dict[str, Any]) -> None:
        code = str(row.get("叶片编号") or "").strip()
        if not code:
            return
        self._ledger[code] = {"grade": row.get("status") or STATUS_ORDER[0]}

    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """对外展示时让「叶片状态」与内部定级保持一致，定级以台账（status）为准。"""
        data = dict(row)
        data["叶片状态"] = row.get("status") or row.get("叶片状态") or ""
        return data
