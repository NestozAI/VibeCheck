"""
HTML to Screenshot Utility
- Convert HTML/CSS code to images
- Used for generating UI mockups
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
    Save HTML content as a screenshot.

    Args:
        html_content: HTML string
        output_path: Output image path
        width: Viewport width
        height: Viewport height
        full_page: Whether to capture the full page

    Returns:
        Saved image path
    """
    # Create temporary HTML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_content)
        temp_html_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': width, 'height': height})

            # Load HTML file
            page.goto(f'file://{temp_html_path}')

            # Wait briefly (for rendering to complete)
            page.wait_for_timeout(500)

            # Save screenshot
            page.screenshot(path=output_path, full_page=full_page)

            browser.close()

        return output_path

    finally:
        # Delete temporary file
        os.unlink(temp_html_path)


def html_file_to_screenshot(
    html_path: str,
    output_path: str,
    width: int = 1200,
    height: int = 800,
    full_page: bool = False
) -> str:
    """
    Save an HTML file as a screenshot.

    Args:
        html_path: HTML file path
        output_path: Output image path
        width: Viewport width
        height: Viewport height
        full_page: Whether to capture the full page

    Returns:
        Saved image path
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})

        # Load HTML file
        page.goto(f'file://{os.path.abspath(html_path)}')

        # Wait briefly (for rendering to complete)
        page.wait_for_timeout(500)

        # Save screenshot
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
    Save a URL as a screenshot.

    Args:
        url: Web URL
        output_path: Output image path
        width: Viewport width
        height: Viewport height
        full_page: Whether to capture the full page

    Returns:
        Saved image path
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})

        # Load URL
        page.goto(url, wait_until='networkidle')

        # Save screenshot
        page.screenshot(path=output_path, full_page=full_page)

        browser.close()

    return output_path


def detect_project_type(project_dir: str) -> dict:
    """
    Detect project type.

    Returns:
        {
            "type": "static" | "node" | "python",
            "framework": "react" | "vue" | "next" | "vite" | "flask" | "fastapi" | None,
            "entry": file or command,
            "port": default port
        }
    """
    import json as json_module

    # Check package.json (Node.js project)
    package_json_path = os.path.join(project_dir, 'package.json')
    if os.path.isfile(package_json_path):
        try:
            with open(package_json_path, 'r') as f:
                pkg = json_module.load(f)

            scripts = pkg.get('scripts', {})
            deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

            # Next.js
            if 'next' in deps:
                return {"type": "node", "framework": "next", "cmd": "npm run dev", "port": 3000}
            # Vite (React, Vue, etc.)
            if 'vite' in deps:
                return {"type": "node", "framework": "vite", "cmd": "npm run dev", "port": 5173}
            # Create React App
            if 'react-scripts' in deps:
                return {"type": "node", "framework": "cra", "cmd": "npm start", "port": 3000}
            # Vue CLI
            if '@vue/cli-service' in deps:
                return {"type": "node", "framework": "vue-cli", "cmd": "npm run serve", "port": 8080}
            # Generic Node.js (if dev script exists)
            if 'dev' in scripts:
                return {"type": "node", "framework": "generic", "cmd": "npm run dev", "port": 3000}
            if 'start' in scripts:
                return {"type": "node", "framework": "generic", "cmd": "npm start", "port": 3000}
        except:
            pass

    # Python project
    if os.path.isfile(os.path.join(project_dir, 'requirements.txt')) or \
       os.path.isfile(os.path.join(project_dir, 'pyproject.toml')):
        # FastAPI
        if os.path.isfile(os.path.join(project_dir, 'main.py')):
            with open(os.path.join(project_dir, 'main.py'), 'r') as f:
                content = f.read()
                if 'fastapi' in content.lower() or 'FastAPI' in content:
                    return {"type": "python", "framework": "fastapi", "cmd": "uvicorn main:app --reload", "port": 8000}
        # Flask
        if os.path.isfile(os.path.join(project_dir, 'app.py')):
            with open(os.path.join(project_dir, 'app.py'), 'r') as f:
                content = f.read()
                if 'flask' in content.lower() or 'Flask' in content:
                    return {"type": "python", "framework": "flask", "cmd": "python app.py", "port": 5000}
        # Streamlit
        for py_file in ['app.py', 'main.py', 'streamlit_app.py']:
            filepath = os.path.join(project_dir, py_file)
            if os.path.isfile(filepath):
                with open(filepath, 'r') as f:
                    if 'streamlit' in f.read().lower():
                        return {"type": "python", "framework": "streamlit", "cmd": f"streamlit run {py_file}", "port": 8501}

    # Static HTML
    if os.path.isfile(os.path.join(project_dir, 'index.html')):
        return {"type": "static", "framework": None, "entry": os.path.join(project_dir, 'index.html'), "port": None}

    # Find HTML files
    html_files = [f for f in os.listdir(project_dir) if f.endswith('.html')]
    if html_files:
        return {"type": "static", "framework": None, "entry": os.path.join(project_dir, html_files[0]), "port": None}

    return {"type": "unknown", "framework": None, "entry": None, "port": None}


def screenshot_project(
    project_dir: str,
    output_path: str,
    width: int = 1200,
    height: int = 800,
    full_page: bool = True,
    timeout: int = 30
) -> str:
    """
    Generate screenshot based on project type.

    - static: Direct screenshot of HTML file
    - node/python: Start dev server then screenshot localhost
    """
    import subprocess
    import time
    import signal

    project_info = detect_project_type(project_dir)
    print(f"Project type detected: {project_info}")

    if project_info["type"] == "static":
        # Static HTML file screenshot
        return html_file_to_screenshot(
            project_info["entry"],
            output_path,
            width=width,
            height=height,
            full_page=full_page
        )

    elif project_info["type"] in ["node", "python"]:
        # Start dev server
        cmd = project_info["cmd"]
        port = project_info["port"]
        url = f"http://localhost:{port}"

        print(f"Starting dev server: {cmd}")

        # Start server process
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create process group
        )

        try:
            # Wait until server is ready
            import socket
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('localhost', port))
                    sock.close()
                    if result == 0:
                        print(f"Server ready: {url}")
                        time.sleep(2)  # Wait for rendering to complete
                        break
                except:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError(f"Server did not start within {timeout} seconds")

            # Take screenshot
            return url_to_screenshot(
                url,
                output_path,
                width=width,
                height=height,
                full_page=full_page
            )

        finally:
            # Terminate server process
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                print("Dev server terminated")
            except:
                pass

    else:
        raise ValueError(f"Unsupported project type: {project_info['type']}")


# Test
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
