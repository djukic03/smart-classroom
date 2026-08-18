from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.v1.dependencies import (
    BearerToken,
    CurrentUser,
    PasswordResetServiceDep,
    SessionServiceDep,
    UserServiceDep,
    client_ip,
    enforce_login_limits,
    enforce_password_reset_limits,
    enforce_register_limit,
    login_account_limiter,
)
from app.core.config import settings
from app.schemas.user import (
    PasswordResetConfirm,
    PasswordResetRequest,
    SessionRead,
    Token,
    UserCreate,
    UserRead,
)

router = APIRouter(tags=["auth"])


def resolve_device_name(sent: str | None, request: Request) -> str:
    if sent and sent.strip():
        return sent.strip()
    user_agent = request.headers.get("User-Agent")
    if user_agent:
        return user_agent[:100]
    return settings.default_device_name


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate, service: UserServiceDep, request: Request
) -> object:
    enforce_register_limit(request)
    return await service.register(data)


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: SessionServiceDep,
    request: Request,
    device_name: Annotated[str | None, Form()] = None,
) -> Token:
    account_key = enforce_login_limits(request, form.username)
    token = await service.login(
        form.username, form.password, resolve_device_name(device_name, request)
    )
    login_account_limiter.reset(account_key)
    return Token(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(token: BearerToken, service: SessionServiceDep) -> None:
    await service.logout(token)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    data: PasswordResetRequest, service: PasswordResetServiceDep, request: Request
) -> dict[str, str]:
    enforce_password_reset_limits(request, data.email)
    await service.request(data.email, client_ip(request))
    return {"detail": "Ako nalog postoji, poslat je link za resetovanje lozinke"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    data: PasswordResetConfirm, service: PasswordResetServiceDep
) -> None:
    await service.reset(data.token, data.new_password)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> object:
    return user


@router.get("/sessions", response_model=list[SessionRead])
async def sessions(user: CurrentUser, service: SessionServiceDep) -> object:
    return await service.list_sessions(user.id)
