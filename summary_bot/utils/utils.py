from functools import cache, wraps
import importlib.metadata
from typing import Any, Awaitable, Callable, Literal

import loguru
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from summary_bot.config import LOGGING_LEVELS, get_settings
from summary_bot.crud.session import get_session_crud
from summary_bot.crud.user import get_user_crud
from summary_bot.models import User
from summary_bot.schemas.sessions import TokenSchema, CreateSession
from summary_bot.schemas.users import GetUser
from summary_bot.utils.security import create_token


@cache
def get_app_version():
    # current installed version in current env
    # for prod - package version (or poetry?)
    # for dev - poetry locked and installed version
    # package name from pyproject.toml
    try:
        return importlib.metadata.version("mats-arm")
    except importlib.metadata.PackageNotFoundError:
        return "<n/a>"


def version_string_generator(api_version) -> str:
    app_version = get_app_version()
    return f"API: {api_version} | APP: {app_version}"


def api_root_path(api_version=None):
    if api_version is None:
        api_version = get_settings().api.base_version
    return f"{get_settings().api.api_prefix}/v{api_version}"


def user_root_path():
    return f"{get_settings().api.api_prefix}"


def dock_path(api_version=None):
    if api_version is None:
        api_version = get_settings().api.base_version
    return api_root_path(api_version) + "/docs#"


def swagger_login_path(api_version=None, login_route="/auth/login-form"):
    if api_version is None:
        api_version = get_settings().api.base_version
    return user_root_path() + login_route


async def get_verified_user(
    session: AsyncSession, username: str, password: str
) -> User:
    """return user or raise HTTPException with 400 status"""
    user_crud = get_user_crud()
    return await user_crud.get_verified_user_by_credentials(
        session, username, password
    )


async def common_create_token(session, user: User) -> TokenSchema:
    """create session row, generate TokenSchema and !commit"""
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    api = get_settings().api

    user: GetUser = GetUser.model_validate(user)

    session = await get_session_crud().create_with_commit(
        session, obj_in=CreateSession(user_id=user.id)
    )

    access_token = create_token(
        session.id,
        session.created_at,
        session.created_at + api.access_timedelta,
    )
    refresh_token = create_token(
        session.refresh_uuid, session.created_at, session.refresh_exp
    )

    loguru.logger.info(
        f"Token created for {user.username} "
        f"({access_token=}, {refresh_token=})"
    )

    return TokenSchema(access_token=access_token, refresh_token=refresh_token)


def log_exception(
    func: Callable[[Any], Awaitable[Any | None]],
    log_level: Literal[LOGGING_LEVELS] = "WARNING",  # type: ignore
):

    @wraps(func)
    async def new_func(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # TODO: how to show traceback in loguru?
            loguru.logger.log(log_level, e)
            return None

    return new_func
