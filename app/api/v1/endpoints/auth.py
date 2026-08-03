from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.v1.dependencies import CurrentUser, UserServiceDep
from app.schemas.user import Token, UserCreate, UserRead

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, service: UserServiceDep) -> object:
    return await service.register(data)


@router.post("/login", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], service: UserServiceDep) -> Token:
    token = await service.login(form.username, form.password)
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> object:
    return user
