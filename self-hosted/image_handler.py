
import os
import re
import glob
import logging
from typing import Set, List, Dict

logger = logging.getLogger(__name__)

# =============================================================================
# 이미지 감지 및 업로드
# =============================================================================

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

def get_existing_images(work_dir: str) -> Set[str]:
    """작업 디렉토리의 기존 이미지 파일 목록 반환"""
    existing = set()
    for ext in IMAGE_EXTENSIONS:
        existing.update(glob.glob(os.path.join(work_dir, f'*{ext}')))
        existing.update(glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True))
    return existing

def get_images_with_mtime(work_dir: str) -> Dict[str, float]:
    """작업 디렉토리의 이미지 파일과 수정 시간 반환"""
    images = {}
    for ext in IMAGE_EXTENSIONS:
        for path in glob.glob(os.path.join(work_dir, f'*{ext}')):
            images[path] = os.path.getmtime(path)
        for path in glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True):
            images[path] = os.path.getmtime(path)
    return images

def find_new_images(work_dir: str, before_images: Set[str]) -> List[str]:
    """새로 생성된 이미지 파일 찾기"""
    after_images = get_existing_images(work_dir)
    new_images = after_images - before_images
    return list(new_images)

def find_new_or_modified_images(work_dir: str, before_images: Dict[str, float]) -> List[str]:
    """새로 생성되거나 수정된 이미지 파일 찾기"""
    after_images = get_images_with_mtime(work_dir)
    result = []
    for path, mtime in after_images.items():
        # 새 파일이거나 수정된 파일
        if path not in before_images or mtime > before_images[path]:
            result.append(path)
    return result

def extract_image_paths_from_response(response: str, work_dir: str) -> List[str]:
    """Claude 응답에서 이미지 파일 경로 추출 (기존 파일만)"""
    image_paths = []

    # 이미지 확장자 패턴
    ext_pattern = '|'.join([ext.replace('.', r'\.') for ext in IMAGE_EXTENSIONS])

    # 절대 경로 패턴: /path/to/image.png
    abs_pattern = rf'(/[a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    abs_matches = re.findall(abs_pattern, response, re.IGNORECASE)

    # 상대 경로 패턴: ./image.png, image.png, path/to/image.png
    rel_pattern = rf'(?:^|[\s`\'"(])([a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    rel_matches = re.findall(rel_pattern, response, re.IGNORECASE)

    all_matches = abs_matches + rel_matches

    for path in all_matches:
        # 경로 정규화
        if path.startswith('/'):
            full_path = path
        else:
            full_path = os.path.join(work_dir, path)

        full_path = os.path.normpath(full_path)

        # 파일이 실제로 존재하는지 확인
        if os.path.isfile(full_path) and full_path not in image_paths:
            image_paths.append(full_path)

    return image_paths


def find_contextual_images(user_message: str, response: str, work_dir: str) -> List[str]:
    """
    사용자 요청과 Claude 응답 컨텍스트를 분석하여 관련 이미지 찾기
    - "그래프 보여줘", "이미지 보여줘" 등의 요청 감지
    - 응답에서 언급된 키워드로 이미지 매칭
    """
    image_paths = []

    # 이미지 요청 키워드
    request_keywords = ['그래프', 'graph', '이미지', 'image', '보여', 'show', '차트', 'chart', 'plot', '시각화']
    combined_text = (user_message + ' ' + response).lower()

    # 키워드가 있는지 확인
    has_image_request = any(kw in combined_text for kw in request_keywords)

    if not has_image_request:
        return []

    # 응답에서 힌트가 될 수 있는 키워드 추출
    hint_patterns = [
        (r'loss[_\s]?curve', 'loss_curve'),
        (r'loss', 'loss'),
        (r'training', 'training'),
        (r'학습', 'loss'),
        (r'그래프', 'graph'),
        (r'chart', 'chart'),
        (r'result', 'result'),
    ]

    # work_dir에서 이미지 파일 찾기
    all_images = get_existing_images(work_dir)

    for img_path in all_images:
        filename = os.path.basename(img_path).lower()

        # 힌트 패턴 매칭
        for pattern, hint in hint_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                if hint in filename or pattern.replace(r'[_\s]?', '').replace('\\', '') in filename:
                    if img_path not in image_paths:
                        image_paths.append(img_path)
                        break

    return image_paths

def upload_images_to_slack(client, channel: str, thread_ts: str, image_paths: List[str], comment_prefix: str = "📊 생성된 이미지", delete_after_upload: bool = False):
    """이미지들을 Slack에 업로드

    Args:
        delete_after_upload: True면 업로드 후 파일 삭제 (screenshot.png 등 임시 파일용)
    """
    for image_path in image_paths:
        try:
            filename = os.path.basename(image_path)
            logger.info(f"이미지 업로드 중: {filename}")

            client.files_upload_v2(
                channel=channel,
                file=image_path,
                filename=filename,
                title=filename,
                thread_ts=thread_ts,
                initial_comment=f"{comment_prefix}: `{filename}`"
            )
            logger.info(f"이미지 업로드 완료: {filename}")

            # 스크린샷 파일은 업로드 후 삭제
            if delete_after_upload or filename.lower() == "screenshot.png":
                try:
                    os.remove(image_path)
                    logger.info(f"임시 이미지 삭제됨: {filename}")
                except Exception as del_e:
                    logger.warning(f"이미지 삭제 실패: {del_e}")
        except Exception as e:
            logger.error(f"이미지 업로드 실패 ({image_path}): {e}")
