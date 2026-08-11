from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserAdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.USER
    is_active: bool = True


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class PasswordUpdate(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_name: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
