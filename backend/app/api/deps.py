"""FastAPI 共用依赖。

auth_required: 管理员鉴权占位——任务 D 合入后替换为真实 JWT 验证。
目前返回 None，所有调用方均可通过，便于并行开发。
"""

from typing import Any


async def auth_required() -> None:
    """占位管理员依赖。任务 D 完成后替换为：
        token: str = Depends(oauth2_scheme)
        return verify_token(token)
    """
    return None
