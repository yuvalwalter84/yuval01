# Render Deployment Configuration

## Playwright Browser Installation

This project uses Playwright for browser automation (see `browser_bot.py`). Render requires special configuration to install the Chromium browser during deployment.

## Configuration Files

### 1. requirements.txt
- ✅ `playwright==1.57.0` is included

### 2. render.yaml
The `render.yaml` file includes the build command that installs Chromium:

```yaml
buildCommand: pip install -r requirements.txt && playwright install --with-deps chromium
```

## Alternative: Render Dashboard Configuration

If you're not using `render.yaml`, configure in the Render dashboard:

1. Go to your service settings
2. Navigate to **Build & Deploy**
3. Set **Build Command** to:
   ```bash
   pip install -r requirements.txt && playwright install --with-deps chromium
   ```
4. Set **Start Command** to:
   ```bash
   streamlit run app.py --server.port $PORT --server.address 0.0.0.0
   ```

## Why `--with-deps`?

The `--with-deps` flag installs system dependencies required by Chromium:
- Libraries for rendering (GTK, etc.)
- Audio/video codecs
- Font libraries
- Other system dependencies

Without this flag, Chromium may fail to launch on Render's Linux environment.

## Verification

After deployment, verify Playwright is working:

```python
# In your application or via Render shell
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        await browser.close()
        print("✅ Playwright working correctly")
```

## Troubleshooting

### ModuleNotFoundError: No module named 'playwright'
- Ensure `playwright==1.57.0` is in `requirements.txt`
- Verify build command includes `playwright install --with-deps chromium`

### Browser launch fails
- Check that `--with-deps` flag is included
- Verify Render instance has sufficient resources (Playwright needs memory)
- Check Render logs for system dependency errors

### Build timeout
- Playwright installation can take 2-3 minutes
- Ensure Render build timeout is set to at least 10 minutes
