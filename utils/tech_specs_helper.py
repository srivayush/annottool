import os
import shutil
import time
import json
import warnings
from tqdm import tqdm
import requests
from requests import HTTPError
import base64
import copy
import warnings
warnings.filterwarnings("ignore")
from .pdf_parsing_utils import generate_text_json_file


def create_folder(folderpath) :
  if not os.path.isdir(folderpath) :
    print('folder path: {} does not exist. creating folder'.format(folderpath))
    os.mkdir(folderpath)
  else :
    print('folder path: {} already exists. deleting all existing files from this folder to copy new files'.format(folderpath) )
    count = 0
    for filename in os.listdir(folderpath) :
      filepath = os.path.join(folderpath, filename)
      os.remove(filepath)
      count +=1
    print('deleted {} existing files from {}'.format(count , folderpath))


# defining function to copy files (all files in the specified folder) from google drive to colab or colab to google drive
def copy_folder(src_folderpath, dst_folderpath) :
  if not os.path.isdir(src_folderpath) :
    print('source folder path: {} does not exist. Returning from function'.format(src_folderpath))
    return None
  create_folder(dst_folderpath)
  print('copying files from source path: {} to destination path: {}'.format(src_folderpath , dst_folderpath))
  src_filenames = os.listdir(src_folderpath)
  count = 0
  for filename in tqdm(src_filenames, total = len(src_filenames)) :
    src_filepath = os.path.join(src_folderpath, filename)
    dst_filepath = os.path.join(dst_folderpath, filename)
    shutil.copy2(src_filepath, dst_folderpath)
    count += 1
  print('\ntotal {} files copied'.format(count))


# defining function to copy a file from google drive to colab or vice-versa
def copy_file(src_filepath, dst_filepath) :
  if not os.path.isfile(src_filepath) :
    print('source file path: {} does not exist. Returning from function'.format(src_filepath))
    return None
  if os.path.isfile(dst_filepath) :
    print('destination file path: {} already exists. Deleting it to copy new file'.format(dst_filepath))
    os.remove(dst_filepath)
  shutil.copy2(src_filepath, dst_filepath)
  print('file copied from source path: {} to destination path: {}'.format(src_filepath , dst_filepath))


class settings:
  # file containing imports settings and authentication credentials

  # app (family name annots tool) db settings
  app_db_host_ip  = 'ai-reco-system-db.c0catrpkqff4.us-east-2.rds.amazonaws.com' # prev ai server - '3.142.131.214' # port is 3306
  app_db_username = 'admin'
  app_db_password = 'admin-ai'
  app_db_name     = 'ai_reco_system'

  # AWS S3 settings
  aws_access_key_id='AKIAVRWGVLHQKWOCJM6U'
  aws_secret_access_key='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'
  s3_bucket_name = 'parspec-ai-reco-system'
  text_bboxes_json_s3_folderpath = 'specsheet_jsons_tech_spec_extraction/'

  # general settings
  max_err_msg_len = 1024
  max_db_allowed_elapsed_time = 99999.999

def download_specsheet_from_url(specsheet_url, specsheet_local_filepath, retry = True):
    print('downloading specsheet_url: {} '.format(specsheet_url))
    specsheet_url = specsheet_url.strip()
    start = time.time() # logging start time
    # encoding the url for proxy server
    #pdf_url = quote(pdf_url)
    #pdf_url = pdf_url.replace(" ", "%20")
    proxy_server_base_path = 'https://wvproxy-staging.parspec.io/controller/rate_limited_download?use_cache=false&url=' # new proxy
    specsheet_proxy_url    = proxy_server_base_path + (base64.urlsafe_b64encode(specsheet_url.encode())).decode()
    #print('specsheet_proxy_url', specsheet_proxy_url)
    # downloading from website
    try :
        response = requests.get(specsheet_proxy_url)
        response_status_code = response.status_code
        response.raise_for_status() # to raise an exception for an unsuccessful status code
        contents = response.content
        with open(specsheet_local_filepath, 'wb') as fh :
            fh.write(contents)
            flag_success_download = True
            err_msg = ""
    except HTTPError as e:
        print('[HTTPError occured]')
        if response_status_code == 429 and retry: ## Retrying for the first time
            print(f"Sleeping for {settings.sleep_time} seconds")
            time.sleep(settings.sleep_time)
            flag_success_download, download_elapsed_time, err_msg = download_specsheet_from_url(specsheet_url, specsheet_local_filepath, retry = False)
            return flag_success_download, download_elapsed_time, err_msg
        print('unable to download specsheet at url:{}, proxy_url:{}'.format(specsheet_url, specsheet_proxy_url))
        print('exception', str(e))
        flag_success_download = False
        max_err_msg_len = settings.max_err_msg_len
        err_msg = '[specsheet_from_mfg_download_error] Exception message: ' + str(e)
        err_msg = err_msg[:max_err_msg_len]
    except Exception as e: #Not an HTTP Error
        print('unable to download specsheet at url:{}, proxy_url:{}'.format(specsheet_url, specsheet_proxy_url))
        print('exception', str(e))
        flag_success_download = False
        max_err_msg_len = settings.max_err_msg_len
        err_msg = '[specsheet_from_mfg_download_error] Exception message: ' + str(e)
        err_msg = err_msg[:max_err_msg_len]
    end  = time.time() # logging end time
    download_elapsed_time = end-start
    download_elapsed_time = round(download_elapsed_time, 2) # round to 2 places after decimal (db constraint DECIMAL(8,3)). (round to 3 decimal places could be used as well)
    max_db_allowed_elapsed_time = settings.max_db_allowed_elapsed_time
    download_elapsed_time = min(download_elapsed_time,max_db_allowed_elapsed_time)
    return flag_success_download, download_elapsed_time, err_msg

def is_valid_box(text_box):
  if text_box["x0"]<0 or text_box["x0"]>1:
    return 0
  elif text_box["y0"]<0 or text_box["y0"]>1:
    return 0
  elif text_box["x1"]<0 or text_box["x1"]>1:
    return 0
  elif text_box["y1"]<0 or text_box["y1"]>1:
    return 0
  else:
    return 1

def exact_match(list_of_text_from_json_file, list_of_matching_word):
  text_info_of_json_file = list_of_text_from_json_file["text_info_list_with_ids"]
  is_present = 0
  outputs = []
  for i in range(len(list_of_matching_word)):
    matching_word_list = list_of_matching_word[i].split(" ")
    # print(matching_word_list)
    len_matching_word_list = len(matching_word_list)
    for j in range(len(text_info_of_json_file)):
      if text_info_of_json_file[j]["text"].lower() != matching_word_list[0].lower():
        continue
      if j+len_matching_word_list <= len(text_info_of_json_file):
        list_to_match = text_info_of_json_file[j:j+len_matching_word_list]
        # print(list_to_match)
        b = [item["text"].lower() for item in list_to_match]
        # print(b)
        if b == matching_word_list:
          is_present = 1
          result = [box for box in text_info_of_json_file[j:j+len_matching_word_list]]
          for res in result:
            outputs.append(res)
  return is_present, outputs

def substring_match(list_of_text_from_json_file, list_of_matching_word):
  text_info_of_json_file = list_of_text_from_json_file["text_info_list_with_ids"]
  is_present = 0
  outputs = []
  for i in range(len(list_of_matching_word)):
    matching_word_list = list_of_matching_word[i].split(" ")
    # print(matching_word_list)
    len_matching_word_list = len(matching_word_list)
    for j in range(len(text_info_of_json_file)):
      # if text_info_of_json_file[j]["text"].lower() not in matching_word_list[0].lower():
      # if matching_word_list[0].lower() not in text_info_of_json_file[j]["text"].lower():
      #   continue
      if len_matching_word_list == 1 and (matching_word_list[0].lower() in text_info_of_json_file[j]["text"].lower()):
        is_present = 1
        outputs.append(text_info_of_json_file[j])
        continue
      if len(matching_word_list[0])>len(text_info_of_json_file[j]["text"]):
        continue
      len_first_index_matching_word = len(matching_word_list[0])
      len_j = len(text_info_of_json_file[j]["text"])
      diff = len_j-len_first_index_matching_word
      if text_info_of_json_file[j]["text"][diff:].lower()!=matching_word_list[0].lower():
        continue
      if j+len_matching_word_list <= len(text_info_of_json_file):
        list_to_match = text_info_of_json_file[j:j+len_matching_word_list]
        # print(list_to_match)
        b = [item["text"].lower() for item in list_to_match]
        # print(b)
        # if len_matching_word_list == 1:
        #   is_present = 1
        #   result = [box for box in text_info_of_json_file[j:j+len_matching_word_list]]
        #   for res in result:
        #     outputs.append(res)
        if len(b[-1]) < len(matching_word_list[-1]):
          continue
        elif (b[1:-1] == matching_word_list[1:-1]) and (matching_word_list[-1] == b[-1][:len(matching_word_list[-1])]):
          is_present = 1
          result = [box for box in text_info_of_json_file[j:j+len_matching_word_list]]
          for res in result:
            outputs.append(res)
  return is_present, outputs

def get_important_keywords(list_of_text_from_json_file, important_keywords_list):
  text_info_of_json_file = list_of_text_from_json_file["text_info_list_with_ids"]
  is_present = 0
  outputs = []
  for i in range(len(important_keywords_list)):
    matching_word_list = important_keywords_list[i].split(" ")
    # print(matching_word_list)
    len_matching_word_list = len(matching_word_list)
    for j in range(len(text_info_of_json_file)):
      # if text_info_of_json_file[j]["text"].lower() not in matching_word_list[0].lower():
      # if matching_word_list[0].lower() not in text_info_of_json_file[j]["text"].lower():
      #   continue
      if len_matching_word_list == 1 and (matching_word_list[0].lower() in text_info_of_json_file[j]["text"].lower()):
        is_present = 1
        outputs.append(text_info_of_json_file[j])
        continue
      if len(matching_word_list[0])>len(text_info_of_json_file[j]["text"]):
        continue
      len_first_index_matching_word = len(matching_word_list[0])
      len_j = len(text_info_of_json_file[j]["text"])
      diff = len_j-len_first_index_matching_word
      if text_info_of_json_file[j]["text"][diff:].lower()!=matching_word_list[0].lower():
        continue
      if j+len_matching_word_list <= len(text_info_of_json_file):
        list_to_match = text_info_of_json_file[j:j+len_matching_word_list]
        # print(list_to_match)
        b = [item["text"].lower() for item in list_to_match]
        # print(b)
        # if len_matching_word_list == 1:
        #   is_present = 1
        #   result = [box for box in text_info_of_json_file[j:j+len_matching_word_list]]
        #   for res in result:
        #     outputs.append(res)
        if len(b[-1]) < len(matching_word_list[-1]):
          continue
        elif (b[1:-1] == matching_word_list[1:-1]) and (matching_word_list[-1] == b[-1][:len(matching_word_list[-1])]):
          is_present = 1
          result = [box for box in text_info_of_json_file[j:j+len_matching_word_list]]
          for res in result:
            outputs.append(res)
  return is_present, outputs

def remove_keywords(list_of_text_from_json_file, remove_keyword_list):
  is_present, outputs = substring_match(list_of_text_from_json_file, remove_keyword_list)
  outputs_copy = copy.deepcopy(outputs)
  id_to_remove = [text["id"] for text in outputs]
  id_to_remove.sort()
  id_to_remove = list(set(id_to_remove))
  i = 0
  j = 0
  while True:
    if j>= len(id_to_remove):
      break
    if id_to_remove[j] == list_of_text_from_json_file["text_info_list_with_ids"][i]["id"]:
      list_of_text_from_json_file["text_info_list_with_ids"][i]["text"] = ""
      j += 1
      i += 1
    else:
      i += 1
  return list_of_text_from_json_file, outputs_copy

######################################

def flex_tape_channel_category_search(list_of_text_from_json_file):
  is_present = 0
  result_luminii_strip = []
  words_for_exact_match_list = ["flexilight", '"channel', "' channel", "channels", "flexible fixtures", "flexible linear led"]
  words_for_substring_match_list = ["tape light", "tapelight", "ropelight", "rope light"]
  words_for_substring_match_and_operator = ["luminii", "strip"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  is_present_luminii, result_luminii = substring_match(list_of_text_from_json_file, ["luminii"])
  is_present_strip, result_strip = substring_match(list_of_text_from_json_file, ["strip"])
  if is_present_luminii and is_present_strip:
    is_present = 1
    result_luminii_strip = result_luminii + result_strip
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match + result_luminii_strip
  else:
    is_present = 0
    result = []
  return is_present, result

def linear_strip_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["' linear", "linear length", "linear multi-directional", "linear indirect", "linear led", "led linear", "linear series", "per linear foot",
                                "linear section", "linear - recessed", "linear downlight", "indirect linear", "direct linear", "bidirectional linear", "suspended linear",
                                "linear suspended", "linear cove", "recessed linear", "linear wrap", "linear pendant", "linear direct"]
  words_for_substring_match_list = ["linear luminaire", "striplights", "strip light", "recessed strip", "strip retrofit", "directional linear", "linear fixtures", "striplight"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def architectural_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["architectural"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def industrial_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["industrial"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def downlight_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["downlight", "downlighting", "up/downlight", "up down light", "up & down light", "install upside down to alter light distribution",
                                    "mounted upwards or downward", "up and down light", "upwards or downward", "down light"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def troffer_panel_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["flat panel"]
  words_for_substring_match_list = ["troffer", "panel"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def decorative_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["decorative"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def floodlight_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["floodlight", "floodlights", "flood lights", "flood light", "track flood", "floodlighting"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def multiples_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["multiples", "multiple spots", "multi-light", "multiform", "multiforms"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def bollard_pathlight_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["bollard", "path light", "pathway fixture"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def landscape_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["landscape", "landscaping", "landscaped", "hardscape"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def area_site_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["site & area", "area lighting", "path and area", "area site"]
  words_for_substring_match_list = ["area luminaire", "security light", "roadway", "area light", "outdoor lighting application"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def high_low_bay_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["high bay", "low bay"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def steplight_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["step light", "steplight", "path finder", "pathfinder", "stair light", "step and wall light", "step/night light"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def cove_perimeter_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["cove", "coves", "perimeter", "cove,"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def ingrade_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["in-grade", "ingrade", "inground", "in-ground"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def vanity_light_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["vanity"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def exit_emergency_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["exit"]
  words_for_substring_match_list = ["emergency light", "emergency lighting system", "emergency heads", "emergency lamps", "exit/emergency"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def cabinet_lighting_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["undercabinet", "under cabinet", "under-cabinet", "slim line bar", "cabinet light", "closet lights"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def wallpack_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["wall pack", "wallpack", "wall-pack"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def parking_garage_canopy_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["parking garage", "parking garages"]
  words_for_substring_match_list = ["canopy mount", "canopy-mount", "canopy light", "canopy luminaire", "canopy series", "parking lots", "mounting : canopy",
                                    "garage light"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def uplight_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["uplight", "up/downlight", "up down light", "up & down light", "up-light", "install upside down to alter light distribution",
                                    "mounted upwards or downward", "upwards or downward", "up and down light"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def cylinder_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["cylinder", "cylindrical", "cylinderical"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def sconce_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["sconce"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def wraparound_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["wrap around", "wraparound", "wrap light", "wrap-around", "wrap luminaire", "residential wrap", "linear wrap"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def fans_category_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["fan", "fans"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

####################
#mounting

def knuckle_yoke_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["knuckle", "yoke"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def adjustable_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["adjustable", "adjustability"]
  words_for_substring_match_list = ["° horizontal", "° vertical aiming", "° vertical tilting", "° indexed vertical aiming"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def arm_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["arm mount", "mounting arm", "extended arm", "mast arm", "pivotable arm", "arm light", "dock arm",
                                "swing arm", "extension arm", "universal arm"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def flush_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["flush mounted", "flush, surface mount design"]
  words_for_substring_match_list = ["flush mount", "flushmount"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def monopoint_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["monopoint", "mono-point"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def recessed_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["recessed"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def semi_flush_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["semi-flush", "semi flush"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def semi_recessed_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["semi-recessed"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def surface_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["surface ceiling"]
  words_for_substring_match_list = ["surface mount", "surface-mount", "surface- or pendant-mounted", "mounted directly on a surface", "suspended or surface",
                                    "surface or suspension mount", "surface or stem mount", "surface luminaire"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def wall_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["mounted on wall", "surface ceiling", "wall mounted", "wall mounts", "wall light", "wall-mount",
                                "wall sconce"]
  words_for_substring_match_list = ["mounts to ceiling or wall", "wall or ceiling mount", "(wall mount)", "wall mount", "wall and surface mount",
                                    "mounting: wall", "mounted on a sloped wall", "wall fan"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def ceiling_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["surface ceiling", "ceiling assembly", "ceiling assembilies", "ceiling mounted"]
  words_for_substring_match_list = ["suspended ceiling", "ceiling opening", "ceiling bracket", "covered ceiling", "existing ceiling", "grid ceiling", "surface ceiling", "ceiling fixture", "ceiling thickness",
                                    "mounts to ceiling", "use in insulated ceiling", "ceiling and wall mount", "wall or ceiling mount", "ceiling installation", "(ceiling mount)",
                                    "accommodate insulated or dropped ceilings", "trim to ceiling", "ceiling mount", "ceiling light", "sloped ceiling", "slope ceiling", "ceiling fan"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def floor_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["surface ceiling", "floor mount", "in-floor", "recessed into a wall or floor", "floor uplight", "floor surface mounted", "floor mounted"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def suspended_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["suspended by", "aircraft cable", "jack chain", "cord set", "hanging mount", "pendant size", "pendent", "stem mount", "stem-mount"]
  words_for_substring_match_list = ["suspend mount", "chandeliers", "pendant", "chain mount", "chain-mount", "suspension mount", "suspended using", "suspended mount", "mounting suspended",
                                    "suspended indirect", "suspended bidirect", "suspension kit", "suspended direct", "suspended linear", "suspended multiform", "cable mount",
                                    "wall mount or suspended", "stem suspended", "direct suspended", "direct suspended"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def t_bar_grid_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["t-grid", "t-bar", "t bar"]
  words_for_substring_match_list = ["t-bar"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def track_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["track lighting", "track light", "track luminaire", "trackhead", "track head", "trac light", "led track",
                                    "flexrail", "track system luminaire", "track miniature"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def flange_trimmed_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["flanged", "trimmable", "trim", "trims", "trimmed", "flange style","trim finish", "flanged option",
                                "flange option", "flange"]
  words_for_substring_match_list = ["flange kit"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def trimless_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["trimless", "trim-less"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def stake_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["stake","stakes"]
  words_for_substring_match_list = ["garden spike", "ground spike"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def retrofit_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = []
  words_for_substring_match_list = ["retrofit"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def magnetic_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["magnetic mount", "magnet mount", "magnet mounting", "magnet clip"]
  words_for_substring_match_list = ["installs magnetically"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def pole_stanchion_tenon_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["pole mount", "post top", "postlite"]
  words_for_substring_match_list = ["posts", "stanchion", "tenon", "post mount", "post lantern"]
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def clamp_mounting_search(list_of_text_from_json_file):
  is_present = 0
  words_for_exact_match_list = ["clamp", "clamp-mount"]
  words_for_substring_match_list = []
  is_present_exact_match, result_exact_match = exact_match(list_of_text_from_json_file, words_for_exact_match_list)
  is_present_substring_match, result_substring_match = substring_match(list_of_text_from_json_file, words_for_substring_match_list)
  if is_present_exact_match or is_present_substring_match:
    is_present = 1
    result = result_exact_match + result_substring_match
  else:
    is_present = 0
    result = []
  return is_present, result

def get_category_mounting_results_all_pages(json_filepath=None, pdf_filepath=None, pdf_link=None, path_to_save_pdf="temp.pdf"):
  try:
    if json_filepath != None:
      f = open(json_filepath)
      file = json.load(f)
    elif pdf_filepath != None:
      a,b,c,d = generate_text_json_file(pdf_filepath)
      file = a
    else:
      flag_success_download, download_elapsed_time, err_msg = download_specsheet_from_url(pdf_link, path_to_save_pdf)
      a,b,c,d = generate_text_json_file(path_to_save_pdf)
      file = a
  except:
    print("error in file or pdf_link")
    return {}
  all_pages_final_result = {}
  pdf_category_all_pages = []
  pdf_mounting_all_pages = []
  category_lists = ["flex_tape_channel", "linear_strip", "architectural", "industrial", "downlight", "troffer_panel", "decorative", "floodlight", "multiples", "bollard_pathlight",
                  "landscape", "area_site", "high_low_bay", "steplight", "cove_perimeter", "ingrade", "vanity_light", "exit_emergency", "cabinet_lighting", "wallpack",
                  "parking_garage_canopy", "uplight", "cylinder", "sconce", "wraparound", "fans"]
  mounting_lists = ["knuckle_yoke", "adjustable", "arm", "flush", "monopoint", "recessed", "semi_flush", "semi_recessed", "surface", "wall", "ceiling", "floor", "suspended", "t_bar_grid",
                    "track", "flange_trimmed", "trimless", "stake", "retrofit", "magnetic", "pole_stanchion_tenon", "clamp"]
  important_word_list = ["mount", "install"]
  remove_keyword_list = ["control panel", "emergency battery pack", "emergency option", "emergency circuit", "emergency battery", "zero-uplight", "% uplight",
                    "optional uplight", "optional soft uplight", "recessed outlet box", "recesses junction box", "cannot be surface mount",
                    "wall mounted controller", "wall mount controller", "flangeless", "mounting channel", "architectural ceiling", "wireless area light",
                    "cannot be surface mount", "surface mount sensor", "diffuser with trim ring", "diffusers w/ trim ring", "diffuser with trims ring",
                    "lens with trim ring", "high-end trim", "integral sensor trim ring", "architectural color", "guide panel", "entire perimeter",
                    "wires exit", "cord exit", "field adjustable", "adjustable cable", "recessed outlet", "trim spring", "spring-less trim",
                    "architectural housing", "emergency lighting control device", "field-adjustable", "edge panel", "optics offered in multiples",
                    "perimeter of the lens", "perimeter of the electrical", "cords exit", "leads exit", "minimize uplight", "adjustable 5-color selecctor",
                    "use with adjustable and eyeball trim", "recessed driver", "slot panel", "acoustic panel", "color panel", "panel and fixture", "panel of",
                    "access panel", "color for panel", "in multiples of", "high bay 360° lens", "watt emergency", "emergency circuit", "emergency batteries",
                    "feed exit", "closed exit", "non-emergency", "zero uplight", "minimal uplight", "uplight shield", "adjustable lumen", "adjustable output",
                    "adjustable light output", "adjustable joiners", " adjustable ac ", "ceiling mount sensor", "seal all gaps between the ceiling", "flange stiffener",
                    "end panel", "glass panel", "adjustable plaster", "monopoint canopy", "cannot be recessed", "driver channel", "aluminum channel", "industrial hygienist",
                    "side panel", "filler panel", "acoustic solutions panel", "panel door", "door panel", "exit from", "wasteful uplight", "with uplight",
                    "with up-light", "no up-light", "up-light module option", "up-light option", "adjustable beam", "ao adjustable", "adjustable dimming",
                    "adjustable low-end", "adjustable high-end", "adjustable time", "recessed or surface j-box", "recessed or surface octagon",
                    "recessed or surface mount horizontal j-box", "recessed j-box", "not suitable for surface mount", "high trim", "low trim", "adjustable cct", "cct adjustable",
                    "adjustable detection", "end trim", "cover panel", "perimeter of", "driver assembly recessed", "uplight is not desired", "uplight is not required", "service panel", "acrylic panel",
                    "per channel", "all channel", "control channel", "channels per"]
  for i in range(1000,10000):
    include_string = "Linear LED {}K".format(i)
    remove_keyword_list.append(include_string)
  file["text_info_list_with_ids"] = [text for text in file["text_info_list_with_ids"] if is_valid_box(text)==1]
  #important word
  is_present_imp_keyword, imp_keywords_outputs = get_important_keywords(file, important_word_list)
  #remove keywords
  file_after_removing_keywords, removed_keywords_outputs = remove_keywords(file, remove_keyword_list)
  for category in category_lists:
    if category == "linear_strip":
      if "flex_tape_channel" in pdf_category_all_pages:
        continue
    if category == "area_site":
      if "landscape" in pdf_category_all_pages or "bollard_pathlight" in pdf_category_all_pages:
        continue
    if category == "cabinet_lighting":
      if "downlight" in pdf_category_all_pages:
        continue
    search_category_function = eval("{}_category_search".format(category))
    is_present, category_result = search_category_function(file_after_removing_keywords)
    if is_present == 1:
      pdf_category_all_pages.append(category)
      all_pages_final_result[category] = category_result
  for mount in mounting_lists:
    search_mount_function = eval("{}_mounting_search".format(mount))
    is_present, mounting_result = search_mount_function(file_after_removing_keywords)
    if is_present == 1:
      pdf_mounting_all_pages.append(mount)
      all_pages_final_result[mount] = mounting_result
  result_dict = {"page_width_height_list":file["page_width_height_list"], "category_mounting_results":all_pages_final_result, "important_keywords":imp_keywords_outputs, "removed_keywords":removed_keywords_outputs }
  return result_dict

def get_category_mounting_results_first_page(json_filepath=None, pdf_filepath=None, pdf_link=None, path_to_save_pdf="temp.pdf"):
  try:
    if json_filepath != None:
      f = open(json_filepath)
      file = json.load(f)
    elif pdf_filepath != None:
      a,b,c,d = generate_text_json_file(pdf_filepath)
      file = a
    else:
      flag_success_download, download_elapsed_time, err_msg = download_specsheet_from_url(pdf_link, path_to_save_pdf)
      a,b,c,d = generate_text_json_file(path_to_save_pdf)
      file = a
  except:
    print("error in file or pdf_link")
    return {}
  first_page_final_result = {}
  pdf_category_first_page = []
  pdf_mounting_first_page = []
  category_lists = ["flex_tape_channel", "linear_strip", "architectural", "industrial", "downlight", "troffer_panel", "decorative", "floodlight", "multiples", "bollard_pathlight",
                  "landscape", "area_site", "high_low_bay", "steplight", "cove_perimeter", "ingrade", "vanity_light", "exit_emergency", "cabinet_lighting", "wallpack",
                  "parking_garage_canopy", "uplight", "cylinder", "sconce", "wraparound", "fans"]
  mounting_lists = ["knuckle_yoke", "adjustable", "arm", "flush", "monopoint", "recessed", "semi_flush", "semi_recessed", "surface", "wall", "ceiling", "floor", "suspended", "t_bar_grid",
                    "track", "flange_trimmed", "trimless", "stake", "retrofit", "magnetic", "pole_stanchion_tenon", "clamp"]
  important_word_list = ["mount", "install"]
  remove_keyword_list = ["control panel", "emergency battery pack", "emergency option", "emergency circuit", "emergency battery", "zero-uplight", "% uplight",
                    "optional uplight", "optional soft uplight", "recessed outlet box", "recesses junction box", "cannot be surface mount",
                    "wall mounted controller", "wall mount controller", "flangeless", "mounting channel", "architectural ceiling", "wireless area light",
                    "cannot be surface mount", "surface mount sensor", "diffuser with trim ring", "diffusers w/ trim ring", "diffuser with trims ring",
                    "lens with trim ring", "high-end trim", "integral sensor trim ring", "architectural color", "guide panel", "entire perimeter",
                    "wires exit", "cord exit", "field adjustable", "adjustable cable", "recessed outlet", "trim spring", "spring-less trim",
                    "architectural housing", "emergency lighting control device", "field-adjustable", "edge panel", "optics offered in multiples",
                    "perimeter of the lens", "perimeter of the electrical", "cords exit", "leads exit", "minimize uplight", "adjustable 5-color selecctor",
                    "use with adjustable and eyeball trim", "recessed driver", "slot panel", "acoustic panel", "color panel", "panel and fixture", "panel of",
                    "access panel", "color for panel", "in multiples of", "high bay 360° lens", "watt emergency", "emergency circuit", "emergency batteries",
                    "feed exit", "closed exit", "non-emergency", "zero uplight", "minimal uplight", "uplight shield", "adjustable lumen", "adjustable output",
                    "adjustable light output", "adjustable joiners", " adjustable ac ", "ceiling mount sensor", "seal all gaps between the ceiling", "flange stiffener",
                    "end panel", "glass panel", "adjustable plaster", "monopoint canopy", "cannot be recessed", "driver channel", "aluminum channel", "industrial hygienist",
                    "side panel", "filler panel", "acoustic solutions panel", "panel door", "door panel", "exit from", "wasteful uplight", "with uplight",
                    "with up-light", "no up-light", "up-light module option", "up-light option", "adjustable beam", "ao adjustable", "adjustable dimming",
                    "adjustable low-end", "adjustable high-end", "adjustable time", "recessed or surface j-box", "recessed or surface octagon",
                    "recessed or surface mount horizontal j-box", "recessed j-box", "not suitable for surface mount", "high trim", "low trim", "adjustable cct", "cct adjustable",
                    "adjustable detection", "end trim", "cover panel", "perimeter of", "driver assembly recessed", "uplight is not desired", "uplight is not required", "service panel", "acrylic panel",
                    "per channel", "all channel", "control channel", "channels per"]
  for i in range(1000,10000):
    include_string = "Linear LED {}K".format(i)
    remove_keyword_list.append(include_string)
  file["text_info_list_with_ids"] = [text for text in file["text_info_list_with_ids"] if text["page_num"]==0]
  file["text_info_list_with_ids"] = [text for text in file["text_info_list_with_ids"] if is_valid_box(text)==1]
  #important word
  is_present_imp_keyword, imp_keywords_outputs = get_important_keywords(file, important_word_list)
  #remove keywords
  file_after_removing_keywords, removed_keywords_outputs = remove_keywords(file, remove_keyword_list)
  for category in category_lists:
    if category == "linear_strip":
      if "flex_tape_channel" in pdf_category_first_page:
        continue
    if category == "area_site":
      if "landscape" in pdf_category_first_page or "bollard_pathlight" in pdf_category_first_page:
        continue
    if category == "cabinet_lighting":
      if "downlight" in pdf_category_first_page:
        continue
    search_category_function = eval("{}_category_search".format(category))
    is_present, category_result = search_category_function(file_after_removing_keywords)
    if is_present == 1:
      pdf_category_first_page.append(category)
      first_page_final_result[category] = category_result
  for mount in mounting_lists:
    search_mount_function = eval("{}_mounting_search".format(mount))
    is_present, mounting_result = search_mount_function(file_after_removing_keywords)
    if is_present == 1:
      pdf_mounting_first_page.append(mount)
      first_page_final_result[mount] = mounting_result
  result_dict = {"page_width_height_list":file["page_width_height_list"], "category_mounting_results":first_page_final_result, "important_keywords":imp_keywords_outputs, "removed_keywords":removed_keywords_outputs }
  return result_dict