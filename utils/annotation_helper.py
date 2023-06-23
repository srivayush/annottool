import io
import base64
from PyPDF2 import PdfFileWriter, PdfFileReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def bounding_box_json_parser(result_dict):
    """
    Final output a dictionary of bounding box coordinates per page and a flag exclude
    """
    page_width_height_list = result_dict["page_width_height_list"] # List of [w,h] for each page
    category_mounting = result_dict["category_mounting_results"] # dict
    important_keywords = result_dict["important_keywords"] # list
    removed_keywords = result_dict["removed_keywords"] # list
    aliases = []
    annotations = {}
    for alias, mapping in category_mounting.items():
        aliases.append(alias)
        if isinstance(mapping, dict) and "include" in mapping.keys() and "exclude" in mapping.keys():
            include_list = mapping["include"]
            exclude_list = mapping["exclude"]
            for item in include_list:
                page_num = item["page_num"]
                w,h = page_width_height_list[page_num]
                if page_num not in annotations.keys():
                     annotations[page_num] = [[w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False]]
                else:
                     annotations[page_num].append([w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False])
            for item in exclude_list:
                if page_num not in annotations.keys():
                     annotations[page_num] = [[w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],True]]
                else:
                     annotations[page_num].append([w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],True])
        else:
            # category_mounting is to be included
            for item in mapping:
                page_num = item["page_num"]
                w,h = page_width_height_list[page_num]
                if page_num not in annotations.keys():
                     annotations[page_num] = [[w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False]]
                else:
                     annotations[page_num].append([w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False])
    if len(important_keywords)>=1:
        aliases.append("Important Keywords")
        for item in important_keywords:
            page_num = item["page_num"]
            w,h = page_width_height_list[page_num]
            if page_num not in annotations.keys():
                annotations[page_num] = [[w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False]]
            else:
                annotations[page_num].append([w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],False])
    if len(removed_keywords)>=1:
        aliases.append("Removed Keywords")
        for item in removed_keywords:
            page_num = item["page_num"]
            w,h = page_width_height_list[page_num]
            if page_num not in annotations.keys():
                annotations[page_num] = [[w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],True]]
            else:
                annotations[page_num].append([w*item["x0"],h*item["y0"],w*item["x1"],h*item["y1"],True])
    return aliases, annotations


def draw_annotations_on_pdf(input_file, output_file, annotations):
    # Open the PDF
    with open(input_file, 'rb') as file:
        pdf = PdfFileReader(file)
        # Create a new PDF writer
        output = PdfFileWriter()
        # Iterate over each page in the PDF
        for page_num in range(pdf.getNumPages()):
            # Validate page numbers in the annotations dictionary
            page = pdf.getPage(page_num)
            # Create a new PDF canvas for the current page
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=letter)
            # Check if annotations are specified for the current page
            if page_num in annotations:
                # Draw the green boxes on the canvas
                for box_info in annotations[page_num]:
                    [x1, y1, x2, y2, exclude] = box_info
                    if exclude:
                        # Transparent red rectangle
                        can.setStrokeColorRGB(1, 0, 0)
                        can.setFillColorRGB(1, 0, 0)
                    else:
                        # Transparent green rectangle
                        can.setStrokeColorRGB(0, 1, 0)
                        can.setFillColorRGB(0, 1, 0)
                    can.setFillAlpha(0.3)
                    can.rect(x1, y1, x2 - x1, y2 - y1, fill=1)
            # Save the canvas
            can.save()
            # Move the pointer to the beginning of the packet
            packet.seek(0)
            new_pdf = PdfFileReader(packet)
            # Merge the modified page with the original PDF
            page.mergePage(new_pdf.getPage(0))
            # Add the modified page to the output PDF
            output.addPage(page)
        # Write the output to a new PDF file
        with open(output_file, 'wb') as out_file:
            output.write(out_file)


def generate_static_html_using_pdf_hash(pdf_path, html_path, aliases):
    pdf_file_path = f"{pdf_path}"
    with open(pdf_file_path, "rb") as file:
        pdf_content = file.read()
        encoded_pdf = base64.b64encode(pdf_content).decode("utf-8")
    pdf_data_uri = f"data:application/pdf;base64,{encoded_pdf}"
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>PDF Viewer</title>
        <style>
            body, html {{
                height: 100%;
                margin: 0;
                padding: 0;
                overflow: hidden;
                background-color: black;
                color: white;
            }}
            .header {{
                background-color: white;
                color: black;
                padding: 10px;
                text-align: center;
                font-size: 20px;
                font-weight: bold;
            }}
            .pdf-viewer {{
                width: 100%;
                height: calc(100% - 30px);
                border: none;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            Currently Selected: {", ".join(aliases)}
        </div>
        <iframe class="pdf-viewer" src="{pdf_data_uri}"></iframe>
    </body>
    </html>
    '''
    with open(html_path, 'w') as file:
        file.write(html_content)
    print(f"HTML file saved successfully at: {html_path}")
    return html_path