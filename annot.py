import os
import hashlib
import time
import requests
import base64
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
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

def stream_file(filepath):
    with open(filepath, "rb") as file:
        while True:
            data = file.read(65536)  # Read in 64KB chunks
            if not data:
                break
            yield data

def generate_annotated_pdf_and_html(pdf_url):
    start_time = time.time()
    url_hash = generate_hash(pdf_url)
    pdf_url = get_proxied_url(pdf_url)
    print("Computed url_hash", url_hash)
    local_filename = f"{url_hash}.pdf"
    output_filename = f"annotated_{url_hash}.pdf"
    html_filename = f"static_{url_hash}.html"
    document_pdf_path = os.path.join(Settings.INPUT_PDF_DIR, local_filename)
    output_pdf_path = os.path.join(Settings.OUTPUT_PDF_DIR, output_filename)
    output_html_filepath = os.path.join(Settings.HTML_DIR, html_filename)    
    if not os.path.exists(document_pdf_path):
        print("Unable to find document_pdf_path locally hence downloading locally....")
        response = requests.get(pdf_url, timeout=10)
        if response.status_code == 200:
            with open(document_pdf_path, "wb") as file:
                file.write(response.content)
        else:
            raise HTTPException(status_code=400, detail="Failed to download PDF file.")
    if not os.path.exists(output_pdf_path):
        exception_in_automation, blank_bounding_boxes = False, False
        print("Unable to find output_pdf_path locally hence generating annotations....")
        try:
            result_dict = get_category_mounting_results_all_pages(pdf_filepath=document_pdf_path)
        except Exception as e:
            exception_in_automation = True
            result_dict = {}
            aliases = []
            aliases_page_1 = []
            annotations = {}
            print("Encountered following exception while generating category mounting results:", e)      
        if result_dict:
            print("Logging result_dict", result_dict)
            aliases, aliases_page_1, annotations = bounding_box_json_parser(result_dict)
            if not annotations:
                blank_bounding_boxes = True
            print("Logging input_file, output_file, aliases, aliases_page_1, annotations", document_pdf_path, output_pdf_path, aliases, aliases_page_1, annotations)
        if annotations:
            print("Drawing annotations on output_pdf_path....")
            draw_annotations_on_pdf(input_file=document_pdf_path, output_file=output_pdf_path, annotations=annotations)
        else:
            if exception_in_automation:
                print("Unable to generate annotations due to exception hence generating output_html_filepath from document_pdf_path...")
            elif blank_bounding_boxes:
                print("Unable to generate annotations due to empty bounding boxes hence generating output_html_filepath from document_pdf_path...")
            else:
                print("SOMETHING WRONG HAS HAPPENED")
            output_html_filepath = generate_static_html_using_pdf_hash2(document_pdf_path, output_html_filepath, aliases, aliases_page_1)
            end_time = time.time()
            print(f"Total time taken to export html: {end_time-start_time} secs")
            return document_pdf_path, output_html_filepath
    if not os.path.exists(output_html_filepath):
        print("Unable to locate output_html_filepath locally hence generating...")
        output_html_filepath = generate_static_html_using_pdf_hash2(output_pdf_path, output_html_filepath, aliases, aliases_page_1)
    end_time = time.time()
    print(f"Total time taken to export html: {end_time-start_time} secs")
    return output_pdf_path, output_html_filepath

app = FastAPI()

@app.get("/")
async def home(pdf_url: str = "", action: str = ""):
    if action == "view_pdf":
        return await view_pdf(pdf_url)
    elif action == "view_html":
        return await view_pdf_viewer_html(pdf_url)
    else:
        return HTMLResponse(content=f"""
        <html>
        <head>
            <style>
                body {{
                    background-color: white;
                    text-align: center;
                    padding-top: 50px;
                }}
                h1 {{
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 20px;
                }}
                p {{
                    font-weight: bold;
                }}
                input[type="text"] {{
                    font-weight: bold;
                    padding: 5px;
                }}
                .btn {{
                    font-weight: bold;
                    padding: 5px 10px;
                    background-color: #006699;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                }}
            </style>
        </head>
        <body>
            <h1>Welcome to the Annotation Tool!</h1>
            <form action="/" method="get" target="_blank">
                <p>PDF URL:</p>
                <input type="text" name="pdf_url" value="{pdf_url}">
                <br><br>
                <button class="btn" type="submit" name="action" value="view_pdf">View PDF</button>
                <button class="btn" type="submit" name="action" value="view_html">View HTML</button>
            </form>
            <p>Please select an action.</p>
        </body>
        </html>
        """, media_type="text/html")

@app.get("/pdf/")
async def view_pdf(pdf_url: str = ""):
    pdf_filepath, _ = generate_annotated_pdf_and_html(pdf_url)
    return FileResponse(pdf_filepath, media_type="application/pdf")

@app.get("/pdf-viewer/")
async def view_pdf_viewer_html(pdf_url: str=""):
    _, html_filepath = generate_annotated_pdf_and_html(pdf_url)
    ############### Streaming response ###############
    # response = StreamingResponse(stream_file(output_html_filepath), media_type="text/html")
    # response.headers["Content-Disposition"] = f'inline; filename="{html_filename}"'
    # return response
    with open(html_filepath, "r") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content, media_type="text/html")