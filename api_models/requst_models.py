from pydantic import BaseModel


class Image_requst(BaseModel):
    clientID : str
    image_url : str


class image_requst_payload(BaseModel):
    clientID : str
    checkType : str | None = "damage"
    image_url : str