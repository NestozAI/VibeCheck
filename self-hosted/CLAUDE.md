# VibeCheck Self-Hosted Agent

## Screenshot Instructions

When the user asks for a screenshot, UI preview, or visual output:

1. **HTML/CSS UI**: If you created an HTML file, use the `mcp__puppeteer__puppeteer_navigate` and `mcp__puppeteer__puppeteer_screenshot` tools:
   - First navigate to the file: `puppeteer_navigate` with `url: "file:///path/to/file.html"`
   - Then take screenshot: `puppeteer_screenshot` with `name: "screenshot"`

2. **Web URL**: For web pages, navigate to the URL first, then screenshot.

3. **Save Location**: Always save screenshots to the current working directory as `screenshot.png` or a descriptive name.

## Example Screenshot Workflow

```
User: "Make a login page and show me a screenshot"

1. Create login.html with the UI
2. Navigate: puppeteer_navigate(url="file:///full/path/to/login.html")
3. Screenshot: puppeteer_screenshot(name="login_screenshot")
```

## Important

- Always use FULL ABSOLUTE paths for local files (e.g., `file:///disk1/lecture/...`)
- The screenshot will be automatically uploaded to Slack by the bot
- Use `width: 1200, height: 800` for good resolution
