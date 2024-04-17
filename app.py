# import required packag
from fastapi import FastAPI, File, UploadFile,Form, Body, Depends, HTTPException, status,BackgroundTasks, Request
from fastapi.responses import JSONResponse
import os
import mimetypes
import logging
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.openapi.models import OpenAPI
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer
from starlette.requests import Request
from starlette.responses import JSONResponse
from api_models import response, requst_models
import datetime
import traceback


from helper_codes import clip_helper, open_ai_helper, aruze_ocr, dbcode, jwt_code, gemini_helper, kfc_ocr
from helper_codes.dbcode import db_log_model, collection_names


description = """
## The Image Processing API Helps with 🤖

### Checking for Product Damage 📦 📁

* You can use this API to check for broken or damaged packages.
* Currently, it supports checking for damaged boxes, damaged packages, and leaks.
* You can view sample images [here](https://drive.google.com/drive/folders/1TzMh0OCPa_BSi19O4zEr0Y284tSOU7fu?usp=drive_link).

### Identifying Product Types 🍏 🍋 🍌 🍉

* This API allows you to determine the product type.
* Please note that it currently supports the identification of eight products: packaged food, apples, mangoes, bananas, oranges, lemons, tomatoes, carrots, and cauliflower.
* Sample images for product type recognition can be found [here](https://drive.google.com/drive/folders/1zq9qZHODjiLMU7BcgI1YRomJmlUYVXRj?usp=drive_link).

### Checking Expiry Dates 📆 🗓️

* With this API, you can extract the manufacturing and expiry dates.
* Dates are provided in DD-MM-YYYY format, and if DD is not present on the product, you will receive MM-YYYY.
* Sample images for checking expiry dates can be found [here](https://drive.google.com/drive/folders/1Z8jXeS4qNtv1OZF2yyTzrwrMF0P74nM7?usp=drive_link).
"""



# set up FastAPI app
app = FastAPI(title="Image Processing",
    summary="Image processing api helps you with all image related issued 🖼️🖼️",
    description=description,
    version="0.0.1", redoc_url=None, docs_url="/image_processing/docs", openapi_prefix="/image_processing",
    contact={
        "name": "Moahmmed Ashraf 👷 , Saransh Sehgal 👷",
        "email": "saransh.sehgal@kapturecrm.com"
    },
    swagger_ui_parameters={"displayRequestDuration":True,"displayOperationId":True})

# setup the new swagger link
@app.get("/image_processing/docs", include_in_schema=False)
def overridden_swagger():
	return get_swagger_ui_html(openapi_url="/image_processing/openapi.json", title="Product Image Analyzer🦸")

@app.get("/image_processing/openapi.json", response_model=OpenAPI, include_in_schema=False)
async def custom_openapi():
    return JSONResponse(app.openapi())


UPLOAD_DIR = "temp_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)



#save the logs in the log file
logging.basicConfig(
    filename="logs/app.log",  # Specify the log file name
    level=logging.INFO,  # Set the logging level (INFO, DEBUG, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Specify log format
)


# add the access origins
origins = ["*"]

#config the origins and handel CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# add the logs in to logfile
@app.middleware("http")
async def log_requests_and_responses(request: Request, call_next):
    # Log the request method and path
    logger = logging.getLogger(__name__)
    logger.info(f"Request: {request.method} {request.url.path}")
    # Proceed with the request
    response = await call_next(request)
    # Log the response status code
    logger.info(f"Response: {response.status_code}")
    return response

# Example route to create a JWT token
@app.post("/image_processing/get-jwt-token/")
async def get_jwt_token(body: dict):
    if 'username' not in body or 'password' not in body:
        return JSONResponse(status_code=400, content={"detail": "username and password is required to generate JWT key."})
    if body.get("username") != os.getenv("JWT_USERNAME") or body.get("password") != os.getenv("JWT_PASSWORD"):
        return JSONResponse(status_code=400, content={"detail": "incorrect username or password provided"})
    data = {"sub": "user_id"}  # Customize this payload as needed
    jwt_token = jwt_code.create_jwt_token(data)
    return {"access_token": jwt_token, "token_type": "bearer"}



@app.post("/image_processing/image_analysis",responses={
    400: {"model": response.code_400, "description": "Bad Request"},
    500: {"model": response.ErrorResponse, "description": "Internal Server Error"}
})
async def Image_Analysis(info : requst_models.image_requst_payload, background_tasks: BackgroundTasks,request: Request, commons: dict = Depends(jwt_code.decode_jwt_token)):
    """
    ### Check If the Product is Damaged or Not 🔍🔍🔍, Expiry Date 📆🗓️ and  Product Type 🍲

    **Required**:
    - **clientID** : An unique id for the client.
    - **image_url**: The image you want to check.
    - **checkType** : Can be ** damage or type or expiry or mrp**

    This endpoint supports images in various formats.

    We support the following product types: 🥫, 🍎, 🍌, 🍋, 🥭, 🍅, 🥕, 🥦.

    You will receive the date information in either DD-MM-YYYY format or MM-YYYY format if the day (DD) is not present on the product.

    Supported image formats include various file types. 📂📄

    Upon successful execution, this endpoint will return a **200** status code ✅.

    In Case We Done Find Any Text In the Image You Will Give  **400** status code.🙅🙅

    In the event of an internal server error, a detailed error response will be provided. ❌🚫🔧

    """
    
    
    try:
        if info.checkType == "damage":
            try:
                check_for_damage = await clip_helper.check_product_is_damaged_or_not(info.image_url)
                filtered_data = [item for item in check_for_damage if item["score"] > 0.55]
                if filtered_data == []:
                    return_data = {"status":"failed",
                                   "status_code":400,
                                   "message":"image is not clear",
                                   "checkType":"damage",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":400,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=400)
                else:
                    response = {"label":filtered_data[0]['label'],"score":filtered_data[0]['score'],"model_full_response":check_for_damage}
                    return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"damage",
                                   "response":response}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":200,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=200)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"damage",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "type":
            try:
                check_for_damage = await clip_helper.check_for_product_type(info.image_url)
                filtered_data = [item for item in check_for_damage if item["score"] > 0.7]
                if filtered_data == []:
                    return_data = {"status":"failed",
                                   "status_code":400,
                                   "message":"image is not clear",
                                   "checkType":"type",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":400,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=400)
                elif filtered_data[0]['label'] == 'None':
                    return_data = {"status":"failed",
                                   "status_code":400,
                                   "message":"image is not clear",
                                   "checkType":"type",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":400,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=400)
                else:
                    response = {"label":filtered_data[0]['label'],"score":filtered_data[0]['score'],"model_full_response":check_for_damage}
                    return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"type",
                                   "response":response}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":200,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=200)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"type",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "expiry":
            try:
                image_text = await aruze_ocr.extract_text_from_image(info.image_url)
                #print("OCR Done...!!!!")
                if image_text == "":
                    return_data = {"status":"failed",
                                   "status_code":400,
                                   "message":"image is not clear",
                                   "checkType":"expiry",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,"ocr_text":image_text,
                            "status_code":400,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                    return JSONResponse(status_code=400,content=return_data)
                else:
                    date_info= await open_ai_helper.extract_dates_with_openai(image_text)
                    print(date_info)
                    new_info = await open_ai_helper.check_for_valid_data(date_info)
                    print(new_info)
                    if "message" in new_info or "error" in new_info:
                        return_data = {"status":"failed",
                                   "status_code":400,
                                   "message":"image is not clear",
                                   "checkType":"expiry",
                                   "response":{}}
                        logdata = {"clientID":info.clientID,"image":info.image_url,"ocr_text":image_text,
                            "status_code":400,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                        log_data = db_log_model(**logdata)
                        dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                        return JSONResponse(status_code=400,content=return_data)
                    else:
                        return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"expiry",
                                   "response":new_info}
                        logdata = {"clientID":info.clientID,"image":info.image_url,"ocr_text":image_text,
                            "status_code":200,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                        log_data = db_log_model(**logdata)
                        dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                    return JSONResponse(status_code=200,content=return_data)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"expiry",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,"ocr_text":image_text,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
    except Exception as e:
        return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":info.checkType,
                                "response":{}}
        logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
        log_data = db_log_model(**logdata)
        dbcode.image_proccesing_logs(collection_name="code_error",data=dict(log_data))
        return JSONResponse(content=return_data, status_code=500)
    


@app.post("/image_processing/image_analysis_v2",responses={
    400: {"model": response.code_400, "description": "Bad Request"},
    500: {"model": response.ErrorResponse, "description": "Internal Server Error"}
})
async def Image_Analysis_V2(info : requst_models.image_requst_payload, background_tasks: BackgroundTasks,request: Request, commons: dict = Depends(jwt_code.decode_jwt_token)):
    """
    ### Check If the Product is Damaged or Not 🔍🔍🔍, Expiry Date 📆🗓️ , Product Type 🍲 and Extract Invoice Data 🧾

    **Required**:
    - **clientID** : An unique id for the client.
    - **image_url**: The image you want to check.
    - **checkType** : Can be ** damage or type or expiry or invoice**

    This endpoint supports images in various formats.

    You will receive the date information in either DD-MM-YYYY format or MM-YYYY format if the day (DD) is not present on the product.

    Supported image formats include various file types. 📂📄

    Upon successful execution, this endpoint will return a **200** status code ✅.

    In Case We Done Find Any Text In the Image You Will Give  **400** status code.🙅🙅

    In the event of an internal server error, a detailed error response will be provided. ❌🚫🔧

    """
    
    
    try:
        logging.info(f"Payload: {info}")
        if info.checkType == "damage":
            try:
                damage_response, status_code = await gemini_helper.product_damage_detection(info.image_url)
                
                if status_code == 500:
                    return_data = {"status":"failed",
                                   "status_code":500,
                                   "message":damage_response["error"],
                                   "checkType":"damage",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=500)
                else:
                    return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"damage",
                                   "response":damage_response}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":200,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=200)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"damage",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['damage'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "type":
            try:
                identification_response, status_code = await gemini_helper.product_identification(info.image_url)
                if status_code == 500:
                    return_data = {"status":"failed",
                                   "status_code":500,
                                   "message":identification_response["error"],
                                   "checkType":"type",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=500)
                else:
                    return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"type",
                                   "response":identification_response}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":200,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=200)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"type",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['type'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "expiry":
            try:
                date_response, status_code = await gemini_helper.product_date_extraction(info.image_url)
                if status_code in [400, 500]:
                    return_data = {"status":"failed",
                                   "status_code":status_code,
                                   "message":date_response["error"],
                                   "checkType":"expiry",
                                   "response":{}}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":status_code,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                    return JSONResponse(status_code=500,content=return_data)
                else:
                    return_data = {"status":"success",
                                "status_code":200,
                                "message":"",
                                "checkType":"expiry",
                                "response":date_response}
                    logdata = {"clientID":info.clientID,"image":info.image_url,
                        "status_code":200,"response":return_data,
                        "log_date_time_in_utc":datetime.datetime.utcnow(),
                        "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                return JSONResponse(status_code=200,content=return_data)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"expiry",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['expiry'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "invoice":
            try:
                invoice_response, extracted_text = await kfc_ocr.get_kfc_invoice_ocr(info.image_url)
                
                return_data = {"status":"success",
                                   "status_code":200,
                                   "message":"",
                                   "checkType":"invoice",
                                   "response":invoice_response}
                logdata = {"clientID":info.clientID,
                           "image":info.image_url,
                            "status_code":200,
                            "response":return_data,
                            "extracted_text": extracted_text,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['invoice'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=200)
            except Exception as e:
                return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":"invoice",
                                "response":{}}
                logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
                log_data = db_log_model(**logdata)
                dbcode.image_proccesing_logs(collection_name=collection_names['invoice'],data=dict(log_data))
                return JSONResponse(content=return_data, status_code=500)
        elif info.checkType == "mrp":
                mrp_response, mrp_status =await gemini_helper.product_MRP_extraction(info.image_url)
                logging.info(f"MRP Processing response resulted with {mrp_response} and status {mrp_status}")
                if mrp_status in [400, 500]:
                    return_data = {
                        "status":"failed",
                        "status_code":mrp_status,
                        "message":mrp_response.get('error'),
                        "checkType":info.checkType,
                        "response":{}
                    }
                    logdata = {
                        "clientID":info.clientID,
                        "image":info.image_url,
                        "status_code":mrp_status,
                        "response":return_data,
                        "log_date_time_in_utc":datetime.datetime.utcnow(),
                        "log_date_time_in_local":str(datetime.datetime.now())}
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['mrp'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=mrp_status)
                else:
                    return_data = {
                        "status":"success",
                        "status_code":mrp_status,
                        "message":"",
                        "checkType":info.checkType,
                        "response":mrp_response
                    }
                    logdata = {
                        "clientID":info.clientID,
                        "image":info.image_url,
                        "mrp":mrp_response.get("mrp"),
                        "status_code":mrp_status,
                        "response":return_data,
                        "log_date_time_in_utc":datetime.datetime.utcnow(),
                        "log_date_time_in_local":str(datetime.datetime.now())
                    }
                    log_data = db_log_model(**logdata)
                    dbcode.image_proccesing_logs(collection_name=collection_names['mrp'],data=dict(log_data))
                    return JSONResponse(content=return_data, status_code=mrp_status)
    except Exception as e:
        traceback.print_exc()
        return_data = {"status":"failed",
                                "status_code":500,
                                "message":str(e),
                                "checkType":info.checkType,
                                "response":{}}
        logdata = {"clientID":info.clientID,"image":info.image_url,
                            "status_code":500,"response":return_data,
                            "log_date_time_in_utc":datetime.datetime.utcnow(),
                            "log_date_time_in_local":str(datetime.datetime.now())}
        log_data = db_log_model(**logdata)
        dbcode.image_proccesing_logs(collection_name="code_error",data=dict(log_data))
        return JSONResponse(content=return_data, status_code=500)
