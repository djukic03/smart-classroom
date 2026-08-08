from pydantic import BaseModel


class MQTTAuthRequest(BaseModel):
    username: str
    password: str

class ACLRequest(BaseModel):
    username: str
    topic: str
    acc: int

class MQTTResponse(BaseModel):
    ok: bool
    error: str = ""
