# installing libraries 
# pip install pdfminer.six
# pip install func-timeout

# importing required libraries 
import time
import pdfminer
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.high_level import extract_text
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams
from pdfminer.layout import LTTextBoxHorizontal, LTTextLineHorizontal, LTChar, LTAnno
from func_timeout import func_timeout, FunctionTimedOut

# defining helper functions 
# defining function to create a new text_dict and initializing with the passed arguments 
def create_new_text_dict(text, page_num, x0,y0,x1,y1) :
  text_dict = dict()
  text_dict['text']     = text
  text_dict['x0']       = x0
  text_dict['y0']       = y0
  text_dict['x1']       = x1 
  text_dict['y1']       = y1
  text_dict['page_num'] = page_num # 0 indexed page number 
  return text_dict

# SOURCE : Camelot https://github.com/camelot-dev/camelot/blob/master/camelot/utils.py
def get_text_objects(layout, ltype="char", t=None):
    if ltype == "char":
        LTObject = LTChar
    elif ltype == "horizontal_text":
        LTObject = LTTextLineHorizontal
    if t is None:
        t = []
    try:
        for obj in layout._objs:
            if isinstance(obj, LTObject):
                t.append(obj)
            else:
                t += get_text_objects(obj, ltype=ltype)
    except AttributeError:
        pass
    return t

# defining a function to process a page with timeout enabled using func-timeout library 
def process_page_with_timeout(interpreter, page_obj):
  interpreter.process_page(page_obj) 

# defining function to get a list of pdfminer layout objects (1 layout object per pdf page) 
def get_pdfminer_layout_list(pdf_filepath) : 
  # defining pdfminer laparams hyper-parameters for pdf text extraction 
  laparams = LAParams(
      line_overlap=0.5, # default 0.5 # group chars into line  
      char_margin=0.2,  # prev used - 0.5 default 2   # group chars into line
      word_margin=1,    # default 0.1 # add spaces between chars 
      line_margin=0.5,  # default 0.5 # group lines into boxes
      all_texts = True
  )  

  page_process_timeout_sec = 15
  layout_list, dim_list = [], []
  # reading and parsing pdf file 
  with open(pdf_filepath, 'rb') as fh : 
    parser   = PDFParser(fh) 
    document = PDFDocument(parser)
    rsrcmgr  = PDFResourceManager()
    device   = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    for page_obj in PDFPage.create_pages(document) : 
      try :
        func_timeout(page_process_timeout_sec, process_page_with_timeout, args=(interpreter, page_obj)) 
        layout = device.get_result() 
        width  = layout.bbox[2]
        height = layout.bbox[3]
        dim    = [width, height] 
      except : # if timed out then exception is of type FunctionTimedOut
         layout = None 
         dim    = None
      layout_list.append(layout)  
      dim_list.append(dim)  

  return layout_list, dim_list 


# defining function to get a list of text words and corresponding bbox coordinates 
# from a list of pdfminer char objects after sorting and combining chars into words 
# assumption is that all chars in char_obj_list belong to a single horizontal line , so sorting only by x0 coordinate can be performed
def get_text_coord_from_char_obj_list(char_obj_list): 
  # sorted char_obj_list by x0 coordinate 
  char_obj_list_sorted = sorted(char_obj_list, key = lambda obj: obj.x0)  
  
  # initializing variables 
  word_text_list, word_coord_list = [], []
  word_text = ''
  word_coord = [ char_obj_list_sorted[0].x0, char_obj_list_sorted[0].y0, char_obj_list_sorted[0].x1, char_obj_list_sorted[0].y1  ]
  whitespace_char = ' ' # single whitespace char 

  # combining chars into words 
  for char_obj in char_obj_list_sorted : 
    if isinstance(char_obj, LTAnno):
      continue
    char_text  = char_obj.get_text()
    char_coord = char_obj.bbox 
    if char_text == whitespace_char : 
      word_text_list.append(word_text) 
      word_coord_list.append(word_coord) 
      word_text  = ''
      word_coord = list(char_coord)
    else : 
      word_text += char_text 
      word_coord = [ min(word_coord[0], char_coord[0]), min(word_coord[1], char_coord[1]),  max(word_coord[2], char_coord[2]), max(word_coord[3], char_coord[3])]
  word_text_list.append(word_text) 
  word_coord_list.append(word_coord)                

  # removing elements where word_text == '' (empty string)
  word_text_list_filtered  = []
  word_coord_list_filtered = []
  for word_text, word_coord in zip(word_text_list , word_coord_list):
    if len(word_text) == 0 : 
      continue 
    word_text_list_filtered.append(word_text) 
    word_coord_list_filtered.append(word_coord)

  return word_text_list_filtered , word_coord_list_filtered

# defining function to get text_list and bbox_coord_list from pdfminer LTTextLine object 
def get_text_bbox_from_LTTextLine(lttextline) : 
  text_list = [] 
  bbox_coord_list  = [] 
  
  # get lttextline obj's text and bbox
  text_lttextline  = lttextline.get_text().strip() 
  coord_lttextline = lttextline.bbox 

  # check if words separated by spaces are present in text 
  whitespace_char = ' '
  if whitespace_char in text_lttextline : 
    char_obj_list = get_text_objects(lttextline, ltype="char")
    text_list , bbox_coord_list = get_text_coord_from_char_obj_list(char_obj_list)
  else : 
    text_list = [text_lttextline] 
    bbox_coord_list = [coord_lttextline]

  return text_list, bbox_coord_list 


# defining function to return all text bboxes in the pdf along with bbox coordinate location, page_number, etc 
def get_text_info_list(pdf_filepath) : 
  start = time.time() # logging start time  
  
  try : 
    err_msg = ""
    
    # getting pdfminer layout objects list (1 per page) 
    layout_list, dim_list  = get_pdfminer_layout_list(pdf_filepath) 
    pdf_page_count = len(layout_list)
  
    text_info_list = [] 
    # getting LTTextLineHorizontal objects for each page 
    for page_num, (layout, dim) in enumerate( zip(layout_list, dim_list) ) : 
      if layout is None : # very likely due to page processing timeout
        err_msg = '[SOFT ERROR]: page_processing_timeout (using func_timeout library)'
        continue
      lttextline_list = get_text_objects(layout, ltype="horizontal_text") 
      page_width, page_height = dim 
      #print('dim', dim) 
  
      for lttextline in lttextline_list : 
        text_list, bbox_coord_list = get_text_bbox_from_LTTextLine(lttextline) 
        for text, (x0,y0,x1,y1) in zip(text_list, bbox_coord_list) : 
          # converting x0,y0,x1,y1 to normalized coordinates
          x0, y0, x1, y1 = x0/page_width, y0/page_height, x1/page_width, y1/page_height 
          text_dict = create_new_text_dict(text, page_num, x0,y0,x1,y1)
          text_info_list.append(text_dict)
    
    # adding id field to text_dict in text_info_list (used in family name annotations tool)
    for id, text_dict in enumerate(text_info_list) : 
      text_dict['id'] = id

  except Exception as e :
    text_info_list = None
    pdf_page_count = None
    err_msg = '[pdf_parsing_error] Exception message: ' + str(e) 
    
  max_err_msg_len = 1024 # settings.max_err_msg_len
  err_msg = err_msg[:max_err_msg_len] 

  end = time.time()
  pdf_parsing_elapsed_time = end - start 
  pdf_parsing_elapsed_time = round(pdf_parsing_elapsed_time,2) # round to 2 places after decimal 
  # max_db_allowed_elapsed_time = settings.max_db_allowed_elapsed_time
  # pdf_parsing_elapsed_time = min(pdf_parsing_elapsed_time, max_db_allowed_elapsed_time)

  return text_info_list, pdf_page_count, pdf_parsing_elapsed_time, err_msg


# defining function to return page_width_height_list. If page cannot be processed within timeout, then returns None for that page width and height
def get_page_width_height_list(specsheet_local_filepath) :
    page_width_height_list = []
    with open(specsheet_local_filepath, 'rb') as fh :
        parser   = PDFParser(fh) 
        doc      = PDFDocument(parser) 
        pdfpages = PDFPage.create_pages(doc) 
        for i, page in enumerate(pdfpages) :
            mediabox   = page.mediabox
            page_width  = mediabox[2]
            page_height = mediabox[3]
            page_rotate_angle = int(page.rotate)
            if page_rotate_angle not in [0, 180] : 
                page_width, page_height = page_height, page_width # swap height and width if page_rotation angle other than 0 or 180 
            page_width_height_list.append([page_width, page_height])

    return page_width_height_list

## Helper function to combine dimensions and text info list
def generate_text_json_file(pdf_filepath):
    return_dict = dict()
    text_info_list, pdf_page_count, pdf_parsing_elapsed_time, err_msg = get_text_info_list(pdf_filepath)
    if text_info_list is not None:
        return_dict["page_width_height_list"] = get_page_width_height_list(pdf_filepath)
        return_dict["text_info_list_with_ids"] = text_info_list
    return return_dict, pdf_page_count, pdf_parsing_elapsed_time, err_msg

if __name__ == "__main__":
    pdf_filepath = "/home/ubuntu/parspec-reco-system/temp/specsheet_pdfs/code_01205150.pdf"
    return_dict = generate_text_json_file(pdf_filepath)
    print(return_dict["page_width_height_list"])
    print(return_dict["text_info_list_with_ids"][:5])