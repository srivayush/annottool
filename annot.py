import os
import hashlib
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from utils.annotation_helper import *
from utils.tech_specs_helper import get_category_mounting_results_all_pages

class Settings:
    BASE_DIR = "/home/ubuntu/annottool"
    INPUT_PDF_DIR = "/home/ubuntu/annottool/pdf/input"
    OUTPUT_PDF_DIR = "/home/ubuntu/annottool/pdf/output"
    HTML_DIR = "/home/ubuntu/annottool/html"
    PROXY_URL = "https://wvproxy-staging.parspec.io/controller/rate_limited_download?url="

def get_proxied_url(url):
    return Settings.PROXY_URL + base64.b64encode(url.encode()).decode()

def generate_hash(url):
    hash_object = hashlib.sha256(url.encode())
    return hash_object.hexdigest()

app = FastAPI()

@app.get("/")
async def home():
    # return HTMLResponse(content='<html><body style="background-color: white; color: black;"><h1>Welcome to the Annotation Tool!</h1><form action="/pdf-viewer/" method="get"><label for="pdf_url">Enter PDF URL:</label><br><input type="text" id="pdf_url" name="pdf_url"><br><br><input type="submit" value="Submit"></form></body></html>', media_type="text/html")
    return """
    <html>
    <head>
        <style>
            body {
                background-color: white;
                text-align: center;
                padding-top: 50px;
            }
            h1 {
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 20px;
            }
            p {
                font-weight: bold;
            }
            input[type="text"] {
                font-weight: bold;
                padding: 5px;
            }
            input[type="submit"] {
                font-weight: bold;
                padding: 5px 10px;
            }
        </style>
    </head>
    <body>
        <h1>Welcome to the Annotation Tool!</h1>
        <form action="/pdf-viewer/" method="get">
            <p>PDF URL:</p>
            <input type="text" name="pdf_url">
            <br><br>
            <input type="submit" value="Submit">
        </form>
    </body>
    </html>
    """

@app.get("/pdf-viewer/")
async def view_pdf_viewer_html(pdf_url: str=""):
    url_hash = generate_hash(pdf_url)
    pdf_url = get_proxied_url(pdf_url)
    print("$$$$$ url_hash", url_hash)
    local_filename = f"{url_hash}.pdf"
    output_filename = f"annotated_{url_hash}.pdf"
    html_filename = f"static_{url_hash}.html"
    document_pdf_path = os.path.join(Settings.INPUT_PDF_DIR, local_filename)
    output_pdf_path = os.path.join(Settings.OUTPUT_PDF_DIR, output_filename)
    output_html_filepath = os.path.join(Settings.HTML_DIR, html_filename)    
    if not os.path.exists(document_pdf_path):
        print("$$$$$ document_pdf_path does not exist hence downloading locally....")
        response = requests.get(pdf_url, timeout=10)
        if response.status_code == 200:
            with open(document_pdf_path, "wb") as file:
                file.write(response.content)
        else:
            raise HTTPException(status_code=400, detail="Failed to download PDF file.")
    if not os.path.exists(output_pdf_path):
        print("$$$$$ output_pdf_path does not exist hence generating annotations....")
        try:
            result_dict = get_category_mounting_results_all_pages(pdf_filepath=document_pdf_path)
        except Exception as e:
            result_dict = {}
            aliases = []
            print("$$$$$ Encountered exception while generating category mounting results:", e)      
        if result_dict:
            print("$$$$$ result_dict", result_dict)
            aliases, annotations = bounding_box_json_parser(result_dict)
            print("$$$$$ input_file, output_file, aliases, annotations", document_pdf_path, output_pdf_path, aliases, annotations)
            if annotations:
                print("$$$$$ drawing annotations on output_pdf_path....")
                draw_annotations_on_pdf(input_file=document_pdf_path, output_file=output_pdf_path, annotations=annotations)
        else:
            print("$$$$$ not able to generate annotations due to exception hence generating output_html_filepath from document_pdf_path...")
            output_html_filepath = generate_static_html_using_pdf_hash(document_pdf_path, output_html_filepath, aliases)
    if not os.path.exists(output_html_filepath):
        print("$$$$$ output_html_filepath does not exist hence generating...")
        output_html_filepath = generate_static_html_using_pdf_hash(output_pdf_path, output_html_filepath, aliases)
    with open(output_html_filepath, "r") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content, media_type="text/html")