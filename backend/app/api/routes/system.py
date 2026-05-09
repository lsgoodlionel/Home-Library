from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.security import require_admin
from app.schemas.system import UpgradeRequest, UpgradeResponse, UpgradeStatusResponse

router = APIRouter()
_UPGRADE_TASKS: dict[str, dict[str, Any]] = {}
_UPGRADE_LOCK = asyncio.Lock()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_upgrade_task(task_id: str, command: str, workdir: str, timeout_seconds: int) -> None:
    async with _UPGRADE_LOCK:
        _UPGRADE_TASKS[task_id]["status"] = "running"
        _UPGRADE_TASKS[task_id]["started_at"] = _utc_now()

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(Path(workdir).resolve()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        status_value = "success" if process.returncode == 0 else "failed"
        async with _UPGRADE_LOCK:
            _UPGRADE_TASKS[task_id].update(
                {
                    "status": status_value,
                    "finished_at": _utc_now(),
                    "exit_code": process.returncode,
                    "output": stdout.decode("utf-8", errors="replace")[-6000:],
                    "error": stderr.decode("utf-8", errors="replace")[-6000:],
                }
            )
    except asyncio.TimeoutError:
        async with _UPGRADE_LOCK:
            _UPGRADE_TASKS[task_id].update(
                {
                    "status": "failed",
                    "finished_at": _utc_now(),
                    "exit_code": None,
                    "error": f"升级命令执行超时（{timeout_seconds} 秒）",
                }
            )
    except Exception as exc:
        async with _UPGRADE_LOCK:
            _UPGRADE_TASKS[task_id].update(
                {
                    "status": "failed",
                    "finished_at": _utc_now(),
                    "exit_code": None,
                    "error": str(exc),
                }
            )


@router.post("/upgrade", response_model=UpgradeResponse)
async def start_upgrade(
    payload: UpgradeRequest,
    _admin: Annotated[object, Depends(require_admin)],
) -> UpgradeResponse:
    settings = get_settings()
    if not settings.upgrade_password or not settings.upgrade_command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="服务器未启用前端升级功能，请配置 UPGRADE_PASSWORD 和 UPGRADE_COMMAND",
        )
    if not secrets.compare_digest(payload.upgrade_password, settings.upgrade_password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="升级专用密码错误")

    async with _UPGRADE_LOCK:
        running = any(task["status"] in {"pending", "running"} for task in _UPGRADE_TASKS.values())
        if running:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有升级任务正在执行")
        task_id = uuid.uuid4().hex
        _UPGRADE_TASKS[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "started_at": _utc_now(),
            "finished_at": None,
            "exit_code": None,
            "output": "",
            "error": "",
        }

    asyncio.create_task(
        _run_upgrade_task(
            task_id,
            settings.upgrade_command,
            settings.upgrade_workdir,
            settings.upgrade_timeout_seconds,
        )
    )
    return UpgradeResponse(task_id=task_id, status="pending", message="升级任务已启动")


@router.get("/upgrade/{task_id}", response_model=UpgradeStatusResponse)
async def get_upgrade_status(
    task_id: str,
    _admin: Annotated[object, Depends(require_admin)],
) -> UpgradeStatusResponse:
    async with _UPGRADE_LOCK:
        task = _UPGRADE_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="升级任务不存在或已清理")
        return UpgradeStatusResponse(**task)
