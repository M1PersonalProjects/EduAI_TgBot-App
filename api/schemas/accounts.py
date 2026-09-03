from pydantic import BaseModel


class WebAppAuthRequest(BaseModel):
    init_data_raw: str


class WebAuthRequest(BaseModel):
    tg_id: int
