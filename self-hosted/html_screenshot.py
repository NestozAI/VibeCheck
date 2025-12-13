"""
HTML to Screenshot Utility
- HTML/CSS 코드를 이미지로 변환
- UI 목업 생성에 사용
"""

import os
import tempfile
from playwright.sync_api import sync_playwright


def html_to_screenshot(
    html_content: str,
    output_path: str,
    width: int = 1200,
    height: int = 800,
    full_page: bool = False
) -> str:
    """
    HTML 콘텐츠를 스크린샷으로 저장

    Args:
        html_content: HTML 문자열
        output_path: 저장할 이미지 경로
        width: 뷰포트 너비
        height: 뷰포트 높이
        full_page: 전체 페이지 캡처 여부

    Returns:
        저장된 이미지 경로
    """
    # 임시 HTML 파일 생성
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_content)
        temp_html_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': width, 'height': height})

            # HTML 파일 로드
            page.goto(f'file://{temp_html_path}')

            # 잠시 대기 (렌더링 완료)
            page.wait_for_timeout(500)

            # 스크린샷 저장
            page.screenshot(path=output_path, full_page=full_page)

            browser.close()

        return output_path

    finally:
        # 임시 파일 삭제
        os.unlink(temp_html_path)


def html_file_to_screenshot(
    html_path: str,
    output_path: str,
    width: int = 1200,
    height: int = 800,
    full_page: bool = False
) -> str:
    """
    HTML 파일을 스크린샷으로 저장

    Args:
        html_path: HTML 파일 경로
        output_path: 저장할 이미지 경로
        width: 뷰포트 너비
        height: 뷰포트 높이
        full_page: 전체 페이지 캡처 여부

    Returns:
        저장된 이미지 경로
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})

        # HTML 파일 로드
        page.goto(f'file://{os.path.abspath(html_path)}')

        # 잠시 대기 (렌더링 완료)
        page.wait_for_timeout(500)

        # 스크린샷 저장
        page.screenshot(path=output_path, full_page=full_page)

        browser.close()

    return output_path


def url_to_screenshot(
    url: str,
    output_path: str,
    width: int = 1200,
    height: int = 800,
    full_page: bool = False
) -> str:
    """
    URL을 스크린샷으로 저장

    Args:
        url: 웹 URL
        output_path: 저장할 이미지 경로
        width: 뷰포트 너비
        height: 뷰포트 높이
        full_page: 전체 페이지 캡처 여부

    Returns:
        저장된 이미지 경로
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})

        # URL 로드
        page.goto(url, wait_until='networkidle')

        # 스크린샷 저장
        page.screenshot(path=output_path, full_page=full_page)

        browser.close()

    return output_path


# 테스트
if __name__ == "__main__":
    test_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .card {
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                width: 400px;
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
                font-size: 24px;
            }
            .input-group {
                margin-bottom: 16px;
            }
            label {
                display: block;
                color: #666;
                margin-bottom: 8px;
                font-size: 14px;
            }
            input {
                width: 100%;
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 16px;
                transition: border-color 0.2s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                margin-top: 10px;
            }
            .footer {
                text-align: center;
                margin-top: 20px;
                color: #999;
                font-size: 14px;
            }
            .footer a {
                color: #667eea;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Login</h1>
            <div class="input-group">
                <label>Email</label>
                <input type="email" placeholder="Enter your email">
            </div>
            <div class="input-group">
                <label>Password</label>
                <input type="password" placeholder="Enter your password">
            </div>
            <button>Sign In</button>
            <div class="footer">
                Don't have an account? <a href="#">Sign up</a>
            </div>
        </div>
    </body>
    </html>
    """

    output = html_to_screenshot(test_html, "test_login_ui.png", width=800, height=600)
    print(f"Screenshot saved: {output}")
