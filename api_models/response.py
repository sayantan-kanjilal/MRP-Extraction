from pydantic import BaseModel




# 500 status code 
class ErrorResponse(BaseModel):
    detail: str


#Clip
class clip_image_processing(BaseModel):
    label : str
    score : int 
    model_full_response : list | None = [{"score": int,
                                          "label": str},
                                          {"score": int,
                                           "label": str}]

class code_400(BaseModel):
    message : str

class expiry(BaseModel):
    Manufacturing_Date: str
    Expiry_Date: str
