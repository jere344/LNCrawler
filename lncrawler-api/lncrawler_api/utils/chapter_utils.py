import json
import os

from django.conf import settings


def check_chapter_path_has_content(chapter_path):
    """
    Check if the chapter file exists and has content
    """
    if chapter_path:
        try:
            full_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, chapter_path)
            if os.path.exists(full_path):
                # If the file is larger than 2KB, we assume it has not failed content and 
                # no need to parse the JSON file
                if os.path.getsize(full_path) > 2048:
                    return True
                else:
                    # If less than 2KB it's ambiguous, either it failed or has little content (only an image)
                    with open(full_path, 'r', encoding='utf-8') as f:
                        chapter_data = json.load(f)
                        body = chapter_data.get('body')
                        fail_message = "Failed to download chapter body"
                        has_content =  body is not None and len(body) > 0 and fail_message not in body
                        if not has_content:
                            # then we delete the file to speed up the next check and to automatically download it
                            # back on the next download
                            os.remove(full_path)
                            return False

                        return True
        except Exception:
            return False
    
    return False
