from dotenv import load_dotenv
import os 
import requests
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser
from PIL import Image
import os
import logging
import json
import regex as re
from dateutil.parser import parse

load_dotenv()  # take environment variables from .env.

subscription_key = os.getenv('subscription_key')
endpoint = os.getenv('endpoint')
GOOGLE_API_KEY=os.getenv('GOOGLE_API_KEY')

async def extract_text_from_image(image_url):

    text_recognition_url = os.path.join(endpoint, "vision/v3.2/read/analyze")

    headers = {'Ocp-Apim-Subscription-Key': subscription_key, 'Content-Type': 'application/json'}
    data = {'url': image_url}
    response = requests.post(text_recognition_url, headers=headers, json=data)

    if response.status_code == 202:
        operation_location = response.headers['Operation-Location']
    else:
        raise Exception('Error:', response.status_code, response.text,data)

    extracted_text = ""
    while True:
        result_response = requests.get(operation_location, headers={'Ocp-Apim-Subscription-Key': subscription_key})
        result = result_response.json()

        if 'analyzeResult' in result:
            lines = result['analyzeResult']['readResults'][0]['lines']
            for line in lines:
                extracted_text += line['text'] + "\n"
            break
    return extracted_text



product_MRP_extraction_prompt = """ You should make sure to always provide the output as a single JSON and no other text. Do not give any warning also in output. Even if you are not getting any MRP don't give any warning as output.
Give the output as a JSON in the following format `{"currency": <currency symbol if available else null>, "mrp": <mrp as float value> or ""}`.
Follow these steps to get the desire result.
Step 1: Identify the text phrases containing the words "MRP", "RS", "USD", "Price","₹","$" only. For example  Do not consider any keywords(e.g: "Net Quatnity","gm","ml" etc.)  other than these. If atleast any of these keywords is not present mrp should be "".
Step 2: Next after you have successfully identified these regions, try to extract the value written after the above words. For example if you have find the text as "Rs: 30.00" then your response should be `{"currency::"Rs", "mrp": "30.00"}`.
Step 3: Analyze the certainty of the extracted MRP. Consider factors like clarity of the image, confidence score of your response.
Step 4: If you are unable to find the desired result or the image is not clear return "mrp" as "" else you give your response in the above mentioned JSON format.

Additional Considerations:

In some cases, the price tags may have digits that are struck through, but these should not be considered part of the price. Below are a few examples to illustrate this:
MRP: Rs~~15.99~~ 12.99
Correctly Extracted Price: 12.99

Handle situations where the MRP might be displayed in a different format, like a range or with discounts.
Account for potential errors in the image or OCR process.
If no clear MRP is found, give MRP as "".

"""





async def gemini_chain_creation(model='gemini-pro', temperature=0):
    llm = ChatGoogleGenerativeAI(model=model, temperature=temperature,google_api_key=GOOGLE_API_KEY)
    parser = JsonOutputParser()
    chain =  llm | parser
    return chain


async def gemini_image_processing(chain, prompt, text):
    request_msg = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "text", "text": text},
        ]
    )
    response_msg = chain.invoke([request_msg])
    return response_msg


async def product_MRP_extraction(text):
    try:
        chain = await gemini_chain_creation()
        response = await gemini_image_processing(chain, product_MRP_extraction_prompt, text)
        if "mrp" not in response:
            #logging.critical("Failed to extract MRP", str(e))
            return {"error": "Something went wrong. Please make sure that the image is clear and the MRP is visible."}, 400
        return response, 200
    except Exception as e:
        #logging.critical("Failed to extract MRP", str(e))
        return {"error": str(e)}, 500