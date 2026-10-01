"""叶片业务规则：台账留底、状态流转、字段校验与筛选口径都收在这里。

叶片编号与定级（叶片状态）以台账这一份为准：即使当期检查记录被清空，
重新登记同一编号时也沿用台账里的原记录 ID 与定级，而不是重置为「待检查」。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "blade"
REQUIRED_FIELDS = ["叶片编号", "所属机组", "叶片长度"]
OPTIONAL_FIELDS = ["制造厂商"]
LIST_FIELDS = ["叶片编号", "所属机组", "叶片长度", "制造厂商", "上次检查日", "裂纹数量", "雷击次数"]
STATUS_ORDER = ["待检查", "完好", "存在裂纹", "已更换"]
ACTION_RULES = {"提交检查": "完好", "登记缺陷": "存在裂纹", "更换叶片": "已更换"}
ACTION_MESSAGES = {"提交检查": "叶片已提交检查", "登记缺陷": "叶片已登记缺陷", "更换叶片": "叶片已更换"}
NEGATIVE_ACTIONS = []

# 叶片台账：叶片编号 -> 台账留底记录。检查记录清空不会清台账，
# 重新登记时编号、记录 ID 与定级都从这里恢复。
_ledger: dict[str, dict[str, Any]] = {}
_ledger_ready = False


def _ensure_ledger() -> None:
    """首次使用时用现有叶片记录把台账垫起来，之后只随登记/动作更新，不随清空消失。"""
    global _ledger_ready
    if _ledger_ready:
        return
    for row in store.rows(MODULE):
        number = str(row.get("叶片编号") or "").strip()
        if number and number not in _ledger:
            _ledger[number] = dict(row)
    _ledger_ready = True


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """对外字段统一用中文列名，定级取内部 status，避免列表与台账两张皮。"""
    item: dict[str, Any] = {"id": row.get("id")}
    for field in LIST_FIELDS:
        item[field] = row.get(field)
    item["叶片状态"] = row.get("status")
    return item


def _find_active(rows: list[dict[str, Any]], number: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("叶片编号") or "").strip() == number:
            return row
    return None


class BladeService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        _ensure_ledger()
        rows = list(store.rows(MODULE))
        if keyword and keyword.strip():
            needle = keyword.strip()
            rows = [row for row in rows if needle in str(row.get("叶片编号", ""))]
        if status and status.strip():
            rows = [row for row in rows if row.get("status") == status.strip()]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        _ensure_ledger()
        row = store.find(MODULE, entry_id)
        return _serialize(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记叶片。

        返回 (记录, 说明)：记录为 None 表示未成功。编号命中台账留底时沿用
        原记录 ID 与定级，只允许更新登记信息；在管编号重复登记会被拦下。
        """
        _ensure_ledger()
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        number = str(values.get("叶片编号")).strip()
        rows = store.rows(MODULE)
        active = _find_active(rows, number)
        if active is not None:
            grade = active.get("status")
            return None, f"叶片编号 {number} 已有在管记录（台账定级：{grade}），请勿重复登记"

        ledger_row = _ledger.get(number)
        if ledger_row is not None:
            # 台账有留底：沿用原 ID 与定级，仅刷新本次登记填报的信息
            entry = dict(ledger_row)
            for field in REQUIRED_FIELDS[1:] + OPTIONAL_FIELDS:
                if str(values.get(field) or "").strip():
                    entry[field] = values.get(field)
            entry["叶片编号"] = number
            rows.append(entry)
            _ledger[number] = dict(entry)
            grade = entry.get("status")
            return _serialize(entry), f"叶片 {number} 已重新登记，定级沿用台账记录：{grade}"

        next_id = max((int(row.get("id", 0)) for row in list(_ledger.values()) + rows), default=0) + 1
        entry: dict[str, Any] = {"id": next_id, "status": STATUS_ORDER[0], "pending": True, "abnormal": False}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            entry[field] = value if str(value or "").strip() else None
        rows.append(entry)
        _ledger[number] = dict(entry)
        return _serialize(entry), "叶片已登记"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        _ensure_ledger()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"叶片 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于叶片可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target == "已更换":
            entry["更换日期"] = date.today().isoformat()
        number = str(entry.get("叶片编号") or "").strip()
        if number:
            _ledger[number] = dict(entry)
        return _serialize(entry), ACTION_MESSAGES.get(action, f"叶片已{action}")

    def stats(self) -> list[dict[str, Any]]:
        """统计只按当期在管记录实时计算，清空后立刻归零，不会残留上一批的数。"""
        _ensure_ledger()
        rows = store.rows(MODULE)
        month_prefix = date.today().strftime("%Y-%m")
        return [
            {"label": "待检查叶片", "value": sum(1 for row in rows if row.get("status") == "待检查")},
            {"label": "存在裂纹叶片", "value": sum(1 for row in rows if row.get("status") == "存在裂纹")},
            {
                "label": "本月更换数",
                "value": sum(
                    1
                    for row in rows
                    if row.get("status") == "已更换"
                    and str(row.get("更换日期", "")).startswith(month_prefix)
                ),
            },
        ]
