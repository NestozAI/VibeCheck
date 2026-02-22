
import os
import re
import glob
import logging
from typing import Set, List, Dict

logger = logging.getLogger(__name__)

# =============================================================================
# Image detection and upload
# =============================================================================

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

def get_existing_images(work_dir: str) -> Set[str]:
    """Return list of existing image files in the working directory"""
    existing = set()
    for ext in IMAGE_EXTENSIONS:
        existing.update(glob.glob(os.path.join(work_dir, f'*{ext}')))
        existing.update(glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True))
    return existing

def get_images_with_mtime(work_dir: str) -> Dict[str, float]:
    """Return image files and their modification times in the working directory"""
    images = {}
    for ext in IMAGE_EXTENSIONS:
        for path in glob.glob(os.path.join(work_dir, f'*{ext}')):
            images[path] = os.path.getmtime(path)
        for path in glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True):
            images[path] = os.path.getmtime(path)
    return images

def find_new_images(work_dir: str, before_images: Set[str]) -> List[str]:
    """Find newly created image files"""
    after_images = get_existing_images(work_dir)
    new_images = after_images - before_images
    return list(new_images)

def find_new_or_modified_images(work_dir: str, before_images: Dict[str, float]) -> List[str]:
    """Find newly created or modified image files"""
    after_images = get_images_with_mtime(work_dir)
    result = []
    for path, mtime in after_images.items():
        # New file or modified file
        if path not in before_images or mtime > before_images[path]:
            result.append(path)
    return result

def extract_image_paths_from_response(response: str, work_dir: str) -> List[str]:
    """Extract image file paths from Claude response (existing files only)"""
    image_paths = []

    # Image extension pattern
    ext_pattern = '|'.join([ext.replace('.', r'\.') for ext in IMAGE_EXTENSIONS])

    # Absolute path pattern: /path/to/image.png
    abs_pattern = rf'(/[a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    abs_matches = re.findall(abs_pattern, response, re.IGNORECASE)

    # Relative path pattern: ./image.png, image.png, path/to/image.png
    rel_pattern = rf'(?:^|[\s`\'"(])([a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    rel_matches = re.findall(rel_pattern, response, re.IGNORECASE)

    all_matches = abs_matches + rel_matches

    for path in all_matches:
        # Normalize path
        if path.startswith('/'):
            full_path = path
        else:
            full_path = os.path.join(work_dir, path)

        full_path = os.path.normpath(full_path)

        # Check if the file actually exists
        if os.path.isfile(full_path) and full_path not in image_paths:
            image_paths.append(full_path)

    return image_paths


def find_contextual_images(user_message: str, response: str, work_dir: str) -> List[str]:
    """
    Find related images by analyzing user request and Claude response context.
    - Detect requests like "show graph", "show image", etc.
    - Match images using keywords mentioned in the response
    """
    image_paths = []

    # Image request keywords
    request_keywords = ['그래프', 'graph', '이미지', 'image', '보여', 'show', '차트', 'chart', 'plot', '시각화']
    combined_text = (user_message + ' ' + response).lower()

    # Check for keywords
    has_image_request = any(kw in combined_text for kw in request_keywords)

    if not has_image_request:
        return []

    # Extract hint keywords from the response
    hint_patterns = [
        (r'loss[_\s]?curve', 'loss_curve'),
        (r'loss', 'loss'),
        (r'training', 'training'),
        (r'학습', 'loss'),
        (r'그래프', 'graph'),
        (r'chart', 'chart'),
        (r'result', 'result'),
    ]

    # Find image files in work_dir
    all_images = get_existing_images(work_dir)

    for img_path in all_images:
        filename = os.path.basename(img_path).lower()

        # Hint pattern matching
        for pattern, hint in hint_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                if hint in filename or pattern.replace(r'[_\s]?', '').replace('\\', '') in filename:
                    if img_path not in image_paths:
                        image_paths.append(img_path)
                        break

    return image_paths

def upload_images_to_slack(client, channel: str, thread_ts: str, image_paths: List[str], comment_prefix: str = "📊 Generated image", delete_after_upload: bool = False):
    """Upload images to Slack.

    Args:
        delete_after_upload: If True, delete files after upload (for temporary files like screenshot.png)
    """
    for image_path in image_paths:
        try:
            filename = os.path.basename(image_path)
            logger.info(f"Uploading image: {filename}")

            client.files_upload_v2(
                channel=channel,
                file=image_path,
                filename=filename,
                title=filename,
                thread_ts=thread_ts,
                initial_comment=f"{comment_prefix}: `{filename}`"
            )
            logger.info(f"Image upload complete: {filename}")

            # Delete screenshot files after upload
            if delete_after_upload or filename.lower() == "screenshot.png":
                try:
                    os.remove(image_path)
                    logger.info(f"Temporary image deleted: {filename}")
                except Exception as del_e:
                    logger.warning(f"Image deletion failed: {del_e}")
        except Exception as e:
            logger.error(f"Image upload failed ({image_path}): {e}")
