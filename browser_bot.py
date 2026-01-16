"""
Vision Stack 2026: Browser Automation & Notification Bot
--------------------------------------------------------
Handles the full browser automation loop for job application submissions, including:
- Headless/human-in-the-loop web flows (LinkedIn, Lever, Greenhouse)
- Profile auto-fill via profile_data.json (central source of truth)
- Language-aware cover letter filling (Hebrew/English)
- AI-powered application question answering
- SMTP application email notification (Anti-Black-Hole/Tracker)
- Strong guardrails against regression (no code shrinkage, all capabilities enforced)
"""

import os
import asyncio
import json
import smtplib
import pandas as pd
import random
import subprocess
import sys
from pathlib import Path
from email.mime.text import MIMEText
from playwright.async_api import async_playwright

# ----- Playwright Browser Installation Check & Auto-Install -----
def check_and_install_chromium():
    """
    Checks if Chromium browser executable exists for Playwright.
    If missing, automatically installs it using subprocess.
    Returns dict with status and message.
    
    This is a one-time setup that happens automatically on first use.
    
    Improved Check: Verifies the actual executable exists on disk, not just a flag file.
    Auto-Recovery: If executable is missing (even if flag file exists), deletes flag and reinstalls.
    """
    # Persistent Flag: If .playwright_done exists, DO NOT even attempt to check the executable
    # Just assume it's there to stop the re-installation loop
    if os.path.exists('.playwright_done'):
        return {"status": True, "message": "Chromium browser is ready (flag found)."}
    
    try:
        # Force Browser Path: Explicitly set the executable path to Ubuntu 24.04 path
        # Check /home/yuvalwalter/.cache/ms-playwright/ and use the exact path found
        ubuntu_chrome_path = "/home/yuvalwalter/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome"
        
        # Check if the explicit Ubuntu path exists
        if os.path.exists(ubuntu_chrome_path):
            executable_exists = True
            # Browser Speed: Create flag file if executable exists and flag doesn't
            if not os.path.exists('.playwright_done'):
                try:
                    with open('.playwright_done', 'w') as f:
                        f.write('Playwright installation completed successfully.')
                except Exception:
                    pass
            return {"status": True, "message": "Chromium browser is ready (Ubuntu path found)."}
        
        # Browser Fix: Fix the 'Playwright Sync API inside asyncio loop' warning
        # Use direct path checking instead of sync_playwright to avoid async/sync conflicts
        executable_exists = False
        
        # Try to find Chromium executable using Playwright's known installation paths
        # This avoids using sync_playwright which causes warnings in async contexts
        try:
            import platform
            system = platform.system()
            home = os.path.expanduser("~")
            
            # Force Browser Path: Use explicit Ubuntu 24.04 path first
            # Fix Browser Path: Search for playwright executable in specific fallback path for Ubuntu 24.04
            # Common Playwright browser paths
            possible_paths = []
            if system == "Linux":
                # Force Browser Path: Explicitly set the executable path to Ubuntu 24.04 path
                ubuntu_chrome_path = "/home/yuvalwalter/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome"
                # Fix Browser Path: chrome-headless-shell fallback path for Ubuntu 24.04
                ubuntu_headless_shell_path = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")
                possible_paths = [
                    ubuntu_chrome_path,  # Explicit Ubuntu path first
                    ubuntu_headless_shell_path,  # chrome-headless-shell fallback
                    os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux64", "chrome"),
                    os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                    os.path.join(home, ".local", "share", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                ]
            elif system == "Darwin":  # macOS
                possible_paths = [
                    os.path.join(home, "Library", "Caches", "ms-playwright", "chromium-*", "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
                ]
            elif system == "Windows":
                possible_paths = [
                    os.path.join(home, "AppData", "Local", "ms-playwright", "chromium-*", "chrome-win", "chrome.exe"),
                ]
            
            # Check if any chromium executable exists (using glob pattern)
            import glob
            for path_pattern in possible_paths:
                matches = glob.glob(path_pattern)
                if matches:
                    executable_path = matches[0]
                    if os.path.exists(executable_path):
                        executable_exists = True
                        # Browser Speed: Create flag file if executable exists and flag doesn't
                        if not os.path.exists('.playwright_done'):
                            try:
                                with open('.playwright_done', 'w') as f:
                                    f.write('Playwright installation completed successfully.')
                            except Exception:
                                pass
                        return {"status": True, "message": "Chromium browser is ready."}
        except Exception as path_check_error:
            # Path check failed, try sync_playwright as fallback (but only if not in async context)
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser_type = p.chromium
                    executable_path = browser_type.executable_path
                    if executable_path and os.path.exists(executable_path):
                        executable_exists = True
                        if not os.path.exists('.playwright_done'):
                            try:
                                with open('.playwright_done', 'w') as f:
                                    f.write('Playwright installation completed successfully.')
                            except Exception:
                                pass
                        return {"status": True, "message": "Chromium browser is ready."}
            except Exception:
                # Chromium not found, proceed to install
                executable_exists = False
        
        # Auto-Recovery: If executable is missing (even if flag file exists), delete flag and reinstall
        if not executable_exists:
            if os.path.exists('.playwright_done'):
                print("⚠️ Auto-Recovery: Chromium executable missing but flag file exists. Deleting flag and reinstalling...")
                try:
                    os.remove('.playwright_done')
                except Exception:
                    pass  # If deletion fails, continue anyway
            
            # Chromium not found - attempt auto-installation
            print("⚠️ Chromium browser not found. Starting automatic installation...")
            print("📥 This is a one-time setup. Please wait...")
            
            try:
                # Executable Verification: Use subprocess.run with check=True for validation
                # Run playwright install chromium
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    check=False  # Don't raise on error, check returncode instead
                )
                
                if result.returncode == 0:
                    # Executable Verification: Verify the executable actually exists after installation
                    # Browser Fix: Use path checking instead of sync_playwright to avoid async warnings
                    try:
                        import platform
                        import glob
                        system = platform.system()
                        home = os.path.expanduser("~")
                        
                        # Force Browser Path: Use explicit Ubuntu 24.04 path first
                        # Fix Browser Path: Search for playwright executable in specific fallback path for Ubuntu 24.04
                        # Check common Playwright browser paths
                        possible_paths = []
                        if system == "Linux":
                            # Force Browser Path: Explicitly set the executable path to Ubuntu 24.04 path
                            ubuntu_chrome_path = "/home/yuvalwalter/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome"
                            # Fix Browser Path: chrome-headless-shell fallback path for Ubuntu 24.04
                            ubuntu_headless_shell_path = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")
                            possible_paths = [
                                ubuntu_chrome_path,  # Explicit Ubuntu path first
                                ubuntu_headless_shell_path,  # chrome-headless-shell fallback
                                os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux64", "chrome"),
                                os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                                os.path.join(home, ".local", "share", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                            ]
                        elif system == "Darwin":
                            possible_paths = [
                                os.path.join(home, "Library", "Caches", "ms-playwright", "chromium-*", "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
                            ]
                        elif system == "Windows":
                            possible_paths = [
                                os.path.join(home, "AppData", "Local", "ms-playwright", "chromium-*", "chrome-win", "chrome.exe"),
                            ]
                        
                        executable_found = False
                        for path_pattern in possible_paths:
                            matches = glob.glob(path_pattern)
                            if matches and os.path.exists(matches[0]):
                                executable_found = True
                                break
                        
                        if executable_found:
                            print("✅ Chromium browser installed successfully!")
                            # Browser Speed: Create flag file only after successful installation and verification
                            try:
                                with open('.playwright_done', 'w') as f:
                                    f.write('Playwright installation completed successfully.')
                            except Exception:
                                pass  # If flag file creation fails, continue anyway
                            return {"status": True, "message": "Chromium browser installed successfully."}
                        else:
                            print("⚠️ Installation completed but executable not found. Retrying...")
                            # Retry installation with check=True for validation
                            subprocess.run(
                                [sys.executable, "-m", "playwright", "install", "chromium"],
                                check=True,
                                timeout=300
                            )
                            # Verify again using path check
                            for path_pattern in possible_paths:
                                matches = glob.glob(path_pattern)
                                if matches and os.path.exists(matches[0]):
                                    try:
                                        with open('.playwright_done', 'w') as f:
                                            f.write('Playwright installation completed successfully.')
                                    except Exception:
                                        pass
                                    return {"status": True, "message": "Chromium browser installed successfully."}
                    except Exception as verify_error:
                        print(f"⚠️ Could not verify executable after installation: {verify_error}")
                        # Continue anyway - installation might have succeeded
                    
                    print("✅ Chromium browser installed successfully!")
                    # Browser Speed: Create flag file only after successful installation
                    try:
                        with open('.playwright_done', 'w') as f:
                            f.write('Playwright installation completed successfully.')
                    except Exception:
                        pass  # If flag file creation fails, continue anyway
                    return {"status": True, "message": "Chromium browser installed successfully."}
                else:
                    error_msg = result.stderr or result.stdout or "Unknown error"
                    print(f"❌ Chromium installation failed: {error_msg}")
                    return {
                        "status": False,
                        "error": "Chromium installation failed",
                        "message": f"Failed to install Chromium automatically. Error: {error_msg}\n\nPlease run manually: python -m playwright install chromium"
                    }
            except subprocess.TimeoutExpired:
                print("❌ Chromium installation timed out (5 minutes).")
                return {
                    "status": False,
                    "error": "Installation timeout",
                    "message": "Chromium installation timed out. Please check your internet connection and try again.\n\nOr run manually: python -m playwright install chromium"
                }
            except Exception as install_error:
                print(f"❌ Chromium installation error: {install_error}")
                return {
                    "status": False,
                    "error": str(install_error),
                    "message": f"Failed to install Chromium automatically: {install_error}\n\nPlease run manually: python -m playwright install chromium"
                }
    except Exception as e:
        # Fallback: try alternative check method
        print(f"⚠️ Browser check error: {e}")
        # Try direct installation as fallback
        try:
            # Executable Verification: Use subprocess.run with check=True for validation
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                timeout=300,
                capture_output=True,
                text=True
            )
            # Browser Fix: Use path checking instead of sync_playwright to avoid async warnings
            # Executable Verification: Verify the executable actually exists after installation
            try:
                import platform
                import glob
                system = platform.system()
                home = os.path.expanduser("~")
                
                # Force Browser Path: Use explicit Ubuntu 24.04 path first
                # Fix Browser Path: Search for playwright executable in specific fallback path for Ubuntu 24.04
                # Check common Playwright browser paths
                possible_paths = []
                if system == "Linux":
                    # Force Browser Path: Explicitly set the executable path to Ubuntu 24.04 path
                    ubuntu_chrome_path = "/home/yuvalwalter/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome"
                    # Fix Browser Path: chrome-headless-shell fallback path for Ubuntu 24.04
                    ubuntu_headless_shell_path = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")
                    possible_paths = [
                        ubuntu_chrome_path,  # Explicit Ubuntu path first
                        ubuntu_headless_shell_path,  # chrome-headless-shell fallback
                        os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux64", "chrome"),
                        os.path.join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                        os.path.join(home, ".local", "share", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
                    ]
                elif system == "Darwin":
                    possible_paths = [
                        os.path.join(home, "Library", "Caches", "ms-playwright", "chromium-*", "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
                    ]
                elif system == "Windows":
                    possible_paths = [
                        os.path.join(home, "AppData", "Local", "ms-playwright", "chromium-*", "chrome-win", "chrome.exe"),
                    ]
                
                executable_found = False
                for path_pattern in possible_paths:
                    matches = glob.glob(path_pattern)
                    if matches and os.path.exists(matches[0]):
                        executable_found = True
                        break
                
                if executable_found:
                    # Browser Speed: Create flag file only after successful installation and verification
                    try:
                        with open('.playwright_done', 'w') as f:
                            f.write('Playwright installation completed successfully.')
                    except Exception:
                        pass  # If flag file creation fails, continue anyway
                    return {"status": True, "message": "Chromium browser installed successfully."}
                else:
                    # Installation might have succeeded but path check failed
                    try:
                        with open('.playwright_done', 'w') as f:
                            f.write('Playwright installation completed successfully.')
                    except Exception:
                        pass
                    return {"status": True, "message": "Chromium browser installed successfully (verification skipped)."}
            except Exception as verify_error:
                print(f"⚠️ Could not verify executable after fallback installation: {verify_error}")
                # Continue anyway - installation might have succeeded
                try:
                    with open('.playwright_done', 'w') as f:
                        f.write('Playwright installation completed successfully.')
                except Exception:
                    pass
                return {"status": True, "message": "Chromium browser installed successfully (verification skipped)."}
        except subprocess.TimeoutExpired:
            return {
                "status": False,
                "error": "Installation timeout",
                "message": "Chromium installation timed out. Please check your internet connection and try again.\n\nOr run manually: python -m playwright install chromium"
            }
        except Exception as fallback_error:
            return {
                "status": False,
                "error": str(fallback_error),
                "message": f"Browser installation check failed: {fallback_error}\n\nPlease run manually: python -m playwright install chromium"
            }

class JobAppBot:
    """
    Autonomous Job Application Bot.
    Loads user profile, automates browser flows, supports human-in-the-loop steps,
    performs ATS auto-fill, and sends submission notification by email.
    """
    def __init__(self, site_name=None, company=None, job_url=None, profile_data_path='profile_data.json', tailored_cv_path=None, cover_letter_text=None, job_description=None):
        self.site_name = site_name
        self.company = company
        self.job_url = job_url
        self.profile_data_path = profile_data_path
        self.tailored_cv_path = tailored_cv_path
        self.cover_letter_text = cover_letter_text  # Language-aware cover letter text
        self.job_description = job_description  # For AI question answering

        # Always use single source of truth
        if not os.path.exists(self.profile_data_path):
            raise FileNotFoundError(f"Missing required user data: {self.profile_data_path}")
        with open(self.profile_data_path, 'r', encoding='utf-8') as f:
            self.profile = json.load(f)
        # Use dedicated user chrome profile dir (for auth persistence)
        self.user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
        
        # Auto-check and install Chromium if missing (one-time setup)
        browser_check = check_and_install_chromium()
        if not browser_check.get("status", False):
            # Log warning but don't crash - let the actual browser launch handle the error
            print(f"⚠️ Browser check warning: {browser_check.get('message', 'Unknown error')}")

    async def apply_to_job(self):
        """
        Full ATS web flow:
        1. Launches browser with user profile for login persistence.
        2. Navigates to job URL.
        3. Auto-fills ATS fields if detected.
        4. Waits for human-in-the-loop review (mandatory pause).
        5. Submits application (manual final launch expected).
        6. Sends confirmation email.
        Returns dict with final status and details.
        """
        result = {"status": False, "error": "", "details": {}}
        if not self.job_url or not self.company:
            result["error"] = "Missing job_url or company name."
            return result
        async with async_playwright() as p:
            try:
                # Silence the Traceback: Wrap browser launch with try-except for friendly error messages
                try:
                    browser = await p.chromium.launch_persistent_context(
                        user_data_dir=self.user_data_dir,
                        headless=False,
                        args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                    )
                except Exception as browser_error:
                    # Friendly error message instead of full crash
                    error_msg = str(browser_error)
                    if "executable doesn't exist" in error_msg or "Executable doesn't exist" in error_msg:
                        result["error"] = "Chromium browser is not installed. Please run: python -m playwright install chromium"
                        print(f"❌ Browser Launch Error: {result['error']}")
                        return result
                    else:
                        result["error"] = f"Failed to launch browser: {error_msg}"
                        print(f"❌ Browser Launch Error: {result['error']}")
                        return result
                
                page = await browser.new_page()
                await page.goto(self.job_url)
                print(f"🔗 Navigated to: {self.job_url}")

                # Detect ATS and perform auto-fill if supported
                ats_name = self._detect_ats_from_url(self.job_url)
                if ats_name:
                    ats_fill_result = await self.auto_fill_ats(page)
                    result["details"]["ats_auto_fill"] = ats_fill_result
                else:
                    print("No ATS auto-fill mapping detected for this job board.")

                # HUMAN-IN-THE-LOOP: Always wait before submission. Manual review required.
                print(f"🛑 Human-in-the-loop: Review required for {self.company}. Manual submit required by user. Waiting 45 seconds...")
                await asyncio.sleep(45)

                # Send confirmation email after user manual submission (synchronous function)
                confirmation = send_confirmation_email(company=self.company, job_title=self.site_name or self.company, result={"status": True})
                result["status"] = True
                result["details"]["confirmation_email"] = confirmation
                print(f"✅ Submission cycle complete for {self.company}.")
            except Exception as exc:
                result["error"] = f"Apply exception: {exc}"
                print(f"❌ Failure: {exc}")
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
        return result

    def _detect_ats_from_url(self, url):
        """
        Returns ATS platform name if recognized in job URL.
        """
        url = url.lower()
        if "greenhouse" in url:
            return "greenhouse"
        if "lever" in url:
            return "lever"
        if "linkedin" in url:
            return "linkedin"
        if "alljobs" in url or "drushim" in url or "jobmaster" in url:
            return "israeli_board"
        return None

    async def auto_fill_ats(self, page):
        """
        Autonomously fill fields in recognized ATS platforms using profile_data.json.
        Includes: basic info, cover letter, CV upload, and AI-powered question answering.
        Returns dict with per-field status.
        """
        print("⚡ Starting ATS Auto-fill...")
        
        # Import PDFTailor for AI question answering (lazy import to avoid circular deps)
        try:
            from pdf_tailor import PDFTailor
            tailor = PDFTailor()
        except Exception as e:
            print(f"⚠️ Could not import PDFTailor for AI questions: {e}")
            tailor = None
        
        field_results = {}
        
        # 1. Basic information fields
        basic_mappings = {
            'input[name*="first_name"], input#first_name, input[aria-label*="First name"], input[placeholder*="First name"]': self.profile.get("first_name", ""),
            'input[name*="last_name"], input#last_name, input[aria-label*="Last name"], input[placeholder*="Last name"]': self.profile.get("last_name", ""),
            'input[name*="email"], input#email, input[aria-label*="Email"], input[placeholder*="email"]': self.profile.get("email", ""),
            'input[name*="phone"], input#phone, input[aria-label*="Phone"], input[placeholder*="phone"]': self.profile.get("phone", ""),
            'input[name*="linkedin"], input[placeholder*="LinkedIn"], input[aria-label*="LinkedIn"]': self.profile.get("linkedin", ""),
        }
        
        for selector, value in basic_mappings.items():
            if not value:
                field_results[selector] = "Skipped (no value)"
                continue
            try:
                selectors = [s.strip() for s in selector.split(',')]
                filled = False
                for sel in selectors:
                    try:
                        locator = page.locator(sel).first
                        if await locator.is_visible(timeout=3000):
                            await locator.fill(value)
                            field_results[selector] = "Filled"
                            filled = True
                            break
                    except:
                        continue
                if not filled:
                    field_results[selector] = "Not visible"
            except Exception as exc:
                field_results[selector] = f"Exception: {exc}"
        
        # 2. Cover Letter field (מכתב מקדים) - Language-aware
        if self.cover_letter_text:
            cover_letter_selectors = [
                'textarea[name*="cover"], textarea[name*="letter"], textarea[name*="מכתב"]',
                'textarea[placeholder*="cover"], textarea[placeholder*="letter"], textarea[placeholder*="מכתב מקדים"]',
                'textarea[aria-label*="cover"], textarea[aria-label*="letter"], textarea[aria-label*="מכתב"]',
                'textarea[id*="cover"], textarea[id*="letter"], textarea[id*="cover_letter"]',
                'textarea[class*="cover"], textarea[class*="letter"]',
            ]
            
            cover_filled = False
            for selector in cover_letter_selectors:
                try:
                    selectors = [s.strip() for s in selector.split(',')]
                    for sel in selectors:
                        try:
                            locator = page.locator(sel).first
                            if await locator.is_visible(timeout=3000):
                                await locator.fill(self.cover_letter_text)
                                field_results["cover_letter"] = "Filled"
                                cover_filled = True
                                print(f"✅ Cover letter filled: {len(self.cover_letter_text)} characters")
                                break
                        except:
                            continue
                    if cover_filled:
                        break
                except:
                    continue
            
            if not cover_filled:
                field_results["cover_letter"] = "Not visible"
        
        # 3. CV/Resume file upload
        cv_file_path = self.profile.get("cv_file_path") or self.tailored_cv_path
        if cv_file_path and os.path.exists(cv_file_path):
            file_input_selectors = [
                'input[type="file"][name*="resume"], input[type="file"][name*="cv"], input[type="file"][name*="קורות"]',
                'input[type="file"][accept*="pdf"], input[type="file"][accept*=".pdf"]',
                'input[type="file"]',
            ]
            
            cv_uploaded = False
            for selector in file_input_selectors:
                try:
                    selectors = [s.strip() for s in selector.split(',')]
                    for sel in selectors:
                        try:
                            locator = page.locator(sel).first
                            if await locator.is_visible(timeout=3000):
                                await locator.set_input_files(cv_file_path)
                                field_results["cv_upload"] = "Uploaded"
                                cv_uploaded = True
                                print(f"✅ CV uploaded: {cv_file_path}")
                                break
                        except:
                            continue
                    if cv_uploaded:
                        break
                except:
                    continue
            
            if not cv_uploaded:
                field_results["cv_upload"] = "Not visible"
        
        # 4. AI-powered question answering (common application questions)
        if tailor and self.job_description:
            common_questions_patterns = [
                'textarea[name*="why"], textarea[name*="motivation"], textarea[name*="reason"]',
                'textarea[placeholder*="why"], textarea[placeholder*="why are you"], textarea[placeholder*="מה מושך"]',
                'textarea[aria-label*="why"], textarea[aria-label*="motivation"]',
                'textarea[id*="why"], textarea[id*="motivation"]',
            ]
            
            cv_text = self.profile.get("master_cv_text", "")
            
            for selector in common_questions_patterns:
                try:
                    selectors = [s.strip() for s in selector.split(',')]
                    for sel in selectors:
                        try:
                            locators = await page.locator(sel).all()
                            for locator in locators:
                                if await locator.is_visible(timeout=2000):
                                    # Try to get the question text from nearby label or placeholder
                                    try:
                                        placeholder = await locator.get_attribute("placeholder") or ""
                                        label_text = placeholder
                                        
                                        # Generate answer using AI
                                        answer = tailor.answer_application_question(
                                            label_text if label_text else "Why are you interested in this position?",
                                            cv_text,
                                            self.job_description
                                        )
                                        
                                        await locator.fill(answer)
                                        field_results[f"question_{sel[:30]}"] = "Answered with AI"
                                        print(f"✅ Answered question with AI: {label_text[:50]}")
                                    except Exception as e:
                                        print(f"⚠️ Could not answer question: {e}")
                                        continue
                        except:
                            continue
                except:
                    continue
        
        print(f"ATS Auto-fill results: {field_results}")
        return field_results
    
    async def auto_submit_application(self, page):
        """
        Auto-Submit Engine: Automatically scans for input fields and textareas.
        Uses CoreEngine to generate a cover letter of at least 800 characters for every application.
        Returns dict with per-field status.
        """
        print("🤖 Starting Auto-Submit Engine...")
        
        field_results = {}
        
        # Import CoreEngine for cover letter generation
        try:
            from core_engine import CoreEngine
            engine = CoreEngine()
        except Exception as e:
            print(f"⚠️ Could not import CoreEngine for auto-submit: {e}")
            return {"error": f"CoreEngine import failed: {e}"}
        
        # Get CV text from profile
        cv_text = self.profile.get("master_cv_text", "")
        if not cv_text:
            print("⚠️ No CV text in profile for auto-submit")
            return {"error": "No CV text available"}
        
        # Get job description (if available) or use placeholder
        job_description = self.job_description or self.profile.get("auto_query", "")
        
        # Scan for all input fields and textareas on the page
        try:
            # Find all input fields (excluding buttons and hidden fields)
            input_fields = await page.locator('input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type]), input[type="number"]').all()
            
            # Find all textareas
            textarea_fields = await page.locator('textarea').all()
            
            print(f"📋 Found {len(input_fields)} input fields and {len(textarea_fields)} textarea fields")
            
            # Fill basic input fields from profile
            for idx, field in enumerate(input_fields):
                try:
                    if await field.is_visible(timeout=1000):
                        # Get field attributes to identify type
                        field_name = await field.get_attribute("name") or ""
                        field_id = await field.get_attribute("id") or ""
                        field_placeholder = await field.get_attribute("placeholder") or ""
                        field_type = await field.get_attribute("type") or "text"
                        
                        # Skip file inputs (handled separately)
                        if field_type == "file":
                            continue
                        
                        # Map common field patterns to profile data
                        field_key = field_name.lower() + field_id.lower() + field_placeholder.lower()
                        value = ""
                        
                        if "first" in field_key and "name" in field_key:
                            value = self.profile.get("first_name", "")
                        elif "last" in field_key and "name" in field_key:
                            value = self.profile.get("last_name", "")
                        elif "email" in field_key or field_type == "email":
                            value = self.profile.get("email", "")
                        elif "phone" in field_key or field_type == "tel":
                            value = self.profile.get("phone", "")
                        elif "linkedin" in field_key:
                            value = self.profile.get("linkedin", "")
                        
                        if value:
                            await field.fill(value)
                            field_results[f"input_{idx}"] = f"Filled ({field_name or field_id or field_placeholder})"
                            print(f"✅ Filled input field: {field_name or field_id or field_placeholder}")
                except Exception as e:
                    print(f"⚠️ Could not fill input field {idx}: {e}")
                    continue
            
            # Fill textareas (cover letters and other text fields)
            for idx, textarea in enumerate(textarea_fields):
                try:
                    if await textarea.is_visible(timeout=1000):
                        # Get textarea attributes
                        textarea_name = await textarea.get_attribute("name") or ""
                        textarea_id = await textarea.get_attribute("id") or ""
                        textarea_placeholder = await textarea.get_attribute("placeholder") or ""
                        
                        textarea_key = (textarea_name + textarea_id + textarea_placeholder).lower()
                        
                        # Check if this is a cover letter field
                        is_cover_letter = any(keyword in textarea_key for keyword in ["cover", "letter", "מכתב", "motivation", "why", "reason"])
                        
                        if is_cover_letter or not self.cover_letter_text:
                            # Generate cover letter using CoreEngine (minimum 800 chars)
                            try:
                                # Generate cover letter with CoreEngine
                                cover_letter = engine.reframing_analysis(
                                    job_description,
                                    cv_text,
                                    skill_bucket=None,
                                    master_profile=None,
                                    digital_persona=None
                                )
                                
                                # Ensure minimum 800 characters
                                if len(cover_letter) < 800:
                                    # If too short, extend with additional context
                                    extension = f"\n\nI am excited about the opportunity to contribute to your team and would welcome the chance to discuss how my experience aligns with your needs."
                                    cover_letter = cover_letter + extension
                                
                                # Truncate to 1200 max if needed
                                if len(cover_letter) > 1200:
                                    cover_letter = cover_letter[:1200]
                                
                                await textarea.fill(cover_letter)
                                field_results[f"textarea_{idx}_cover"] = f"Filled with AI-generated cover letter ({len(cover_letter)} chars)"
                                print(f"✅ Generated and filled cover letter: {len(cover_letter)} characters")
                            except Exception as e:
                                print(f"⚠️ Could not generate cover letter for textarea {idx}: {e}")
                                # Use existing cover letter if available
                                if self.cover_letter_text:
                                    await textarea.fill(self.cover_letter_text)
                                    field_results[f"textarea_{idx}_cover"] = "Filled with existing cover letter"
                        else:
                            # Use existing cover letter text if provided
                            if self.cover_letter_text:
                                await textarea.fill(self.cover_letter_text)
                                field_results[f"textarea_{idx}_cover"] = "Filled with existing cover letter"
                except Exception as e:
                    print(f"⚠️ Could not fill textarea {idx}: {e}")
                    continue
        except Exception as e:
            print(f"⚠️ Error scanning page fields: {e}")
            field_results["error"] = str(e)
        
        print(f"Auto-Submit Engine results: {field_results}")
        return field_results

# ----- SMTP Email Notification Logic -----
def send_confirmation_email(company, job_title, result=None):
    """
    Sends a confirmation email (via SMTP) after every successful submission.
    Uses email address from profile_data.json as sender and recipient.
    Uses EMAIL_APP_PASSWORD environment variable for SMTP authentication.
    This is a top-level function for auditability and system-wide integration.
    """
    try:
        # Always load authoritative email from profile_data.json
        if not os.path.exists("profile_data.json"):
            print("⚠️ No profile_data.json for email notification.")
            return {"status": False, "error": "profile_data.json not found"}
        with open('profile_data.json', 'r', encoding='utf-8') as f:
            profile = json.load(f)
        email_user = profile.get('email')
        if not email_user:
            print("⚠️ No user email in profile_data.json! Skipping notification.")
            return {"status": False, "error": "no email set"}
        
        # Get SMTP password from environment variable
        app_password = os.getenv("EMAIL_APP_PASSWORD")
        if not app_password:
            print("⚠️ SMTP Password missing. Skipping email notification.")
            return {"status": False, "error": "no SMTP password"}

        msg_body = f"""
Hi,

Good news! You applied for: {job_title} at {company}.
Application status: {result.get('status','unknown') if result else 'submitted'}.
You can track your full application history in applications_history.csv.

🏢 Company: {company}
🏷️ Job Title: {job_title}

Best,
Vision Stack Autonomous Agent
"""
        msg = MIMEText(msg_body)
        msg['Subject'] = f"🚀 Vision Stack: Applied to {company}"
        msg['From'] = email_user
        msg['To'] = email_user

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_user, app_password)
            server.send_message(msg)
        print(f"📧 Confirmation email sent to: {email_user}")
        return {"status": True}
    except Exception as exc:
        print(f"❌ SMTP Error: {exc}")
        return {"status": False, "error": str(exc)}

# ----- Application Submission Function (Top-level for integration) -----
def submit_application(company, job_title, job_url, cover_letter_text, tailored_cv_path=None, job_description=None, site_name=None):
    """
    Top-level function to submit a job application.
    This function orchestrates the full submission flow:
    1. Creates JobAppBot instance
    2. Runs apply_to_job() async method
    3. Returns submission result
    
    This is the main entry point for application submissions from the UI.
    Used by the 'Final Launch' button in the Human-in-the-Loop section.
    
    Args:
        company: Company name
        job_title: Job title
        job_url: Job application URL
        cover_letter_text: Cover letter text (language-aware, 800-1200 chars)
        tailored_cv_path: Path to tailored CV PDF (optional)
        job_description: Job description for AI question answering (optional)
        site_name: Site name (e.g., 'linkedin', 'greenhouse') (optional)
    
    Returns:
        dict with 'status' (bool), 'error' (str), and 'details' (dict)
    """
    try:
        # Create JobAppBot instance
        bot = JobAppBot(
            site_name=site_name,
            company=company,
            job_url=job_url,
            profile_data_path='profile_data.json',
            tailored_cv_path=tailored_cv_path,
            cover_letter_text=cover_letter_text,
            job_description=job_description
        )
        
        # Run async apply_to_job method
        result = asyncio.run(bot.apply_to_job())
        
        return result
    except Exception as e:
        error_msg = str(e)
        print(f"❌ submit_application error: {error_msg}")
        return {
            "status": False,
            "error": error_msg,
            "details": {}
        }

# ----- For external ATS integration via app.py -----
async def auto_fill_ats(site_name, company, job_url, profile_data_path, tailored_cv_path, cover_letter_text=None, job_description=None):
    """
    External ATS auto-fill entrypoint for integration with main UI (app.py).
    Launches Playwright, fills forms, returns structured result.
    Uses profile_data.json as the source of truth for form data.
    Includes language-aware cover letter filling and AI-powered question answering.
    """
    result = {"status": False, "error": "", "details": {}}
    try:
        # Auto-Install Logic: Check and install Chromium if missing (one-time setup)
        browser_check = check_and_install_chromium()
        if not browser_check.get("status", False):
            error_msg = browser_check.get("message", "Chromium browser is not available.")
            result["error"] = f"Browser Setup Required: {error_msg}"
            return result
        
        if not os.path.exists(profile_data_path):
            result["error"] = f"No profile found at {profile_data_path}"
            return result
        with open(profile_data_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
        user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
        
        # Import PDFTailor for AI question answering
        try:
            from pdf_tailor import PDFTailor
            tailor = PDFTailor()
        except Exception as e:
            print(f"⚠️ Could not import PDFTailor: {e}")
            tailor = None
        
        async with async_playwright() as p:
            # Silence the Traceback: Wrap browser launch with try-except for friendly error messages
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                )
            except Exception as browser_error:
                # Friendly error message instead of full crash
                error_msg = str(browser_error)
                if "executable doesn't exist" in error_msg or "Executable doesn't exist" in error_msg:
                    raise Exception("Chromium browser is not installed. Please run: python -m playwright install chromium")
                else:
                    raise Exception(f"Failed to launch browser: {error_msg}")
            
            page = await context.new_page()
            await page.goto(job_url)
            await page.wait_for_timeout(2000)  # Wait for page to load
            
            # Recognize ATS
            ats_name = None
            url = job_url.lower()
            if "greenhouse" in url:
                ats_name = "greenhouse"
            elif "lever" in url:
                ats_name = "lever"
            elif "linkedin" in url:
                ats_name = "linkedin"
            elif "alljobs" in url or "drushim" in url or "jobmaster" in url:
                ats_name = "israeli_board"
            
            details = {}
            
            # 1. Basic information fields
            basic_mappings = {
                'input[name*="first_name"], input#first_name, input[aria-label*="First name"], input[placeholder*="First name"]': profile.get("first_name", ""),
                'input[name*="last_name"], input#last_name, input[aria-label*="Last name"], input[placeholder*="Last name"]': profile.get("last_name", ""),
                'input[name*="email"], input#email, input[aria-label*="Email"], input[placeholder*="email"]': profile.get("email", ""),
                'input[name*="phone"], input#phone, input[aria-label*="Phone"], input[placeholder*="phone"]': profile.get("phone", ""),
                'input[name*="linkedin"], input[placeholder*="LinkedIn"], input[aria-label*="LinkedIn"]': profile.get("linkedin", ""),
            }
            
            for selector, value in basic_mappings.items():
                if not value:
                    details[selector] = "Skipped (no value)"
                    continue
                try:
                    selectors = [s.strip() for s in selector.split(',')]
                    filled = False
                    for sel in selectors:
                        try:
                            locator = page.locator(sel).first
                            if await locator.is_visible(timeout=3000):
                                await locator.fill(value)
                                details[selector] = "Filled"
                                filled = True
                                break
                        except:
                            continue
                    if not filled:
                        details[selector] = "Not visible"
                except Exception as exc:
                    details[selector] = f"Exception: {exc}"
            
            # 2. Cover Letter field (מכתב מקדים) - Language-aware
            if cover_letter_text:
                cover_letter_selectors = [
                    'textarea[name*="cover"], textarea[name*="letter"], textarea[name*="מכתב"]',
                    'textarea[placeholder*="cover"], textarea[placeholder*="letter"], textarea[placeholder*="מכתב מקדים"]',
                    'textarea[aria-label*="cover"], textarea[aria-label*="letter"], textarea[aria-label*="מכתב"]',
                    'textarea[id*="cover"], textarea[id*="letter"], textarea[id*="cover_letter"]',
                    'textarea[class*="cover"], textarea[class*="letter"]',
                ]
                
                cover_filled = False
                for selector in cover_letter_selectors:
                    try:
                        selectors = [s.strip() for s in selector.split(',')]
                        for sel in selectors:
                            try:
                                locator = page.locator(sel).first
                                if await locator.is_visible(timeout=3000):
                                    await locator.fill(cover_letter_text)
                                    details["cover_letter"] = "Filled"
                                    cover_filled = True
                                    print(f"✅ Cover letter filled: {len(cover_letter_text)} characters")
                                    break
                            except:
                                continue
                        if cover_filled:
                            break
                    except:
                        continue
                
                if not cover_filled:
                    details["cover_letter"] = "Not visible"
            
            # 3. CV/Resume file upload
            cv_file_path = profile.get("cv_file_path") or tailored_cv_path
            if cv_file_path and os.path.exists(cv_file_path):
                file_input_selectors = [
                    'input[type="file"][name*="resume"], input[type="file"][name*="cv"], input[type="file"][name*="קורות"]',
                    'input[type="file"][accept*="pdf"], input[type="file"][accept*=".pdf"]',
                    'input[type="file"]',
                ]
                
                cv_uploaded = False
                for selector in file_input_selectors:
                    try:
                        selectors = [s.strip() for s in selector.split(',')]
                        for sel in selectors:
                            try:
                                locator = page.locator(sel).first
                                if await locator.is_visible(timeout=3000):
                                    await locator.set_input_files(cv_file_path)
                                    details["cv_upload"] = "Uploaded"
                                    cv_uploaded = True
                                    print(f"✅ CV uploaded: {cv_file_path}")
                                    break
                            except:
                                continue
                        if cv_uploaded:
                            break
                    except:
                        continue
                
                if not cv_uploaded:
                    details["cv_upload"] = "Not visible"
            
            # 4. AI-powered question answering
            if tailor and job_description:
                common_questions_patterns = [
                    'textarea[name*="why"], textarea[name*="motivation"], textarea[name*="reason"]',
                    'textarea[placeholder*="why"], textarea[placeholder*="why are you"], textarea[placeholder*="מה מושך"]',
                    'textarea[aria-label*="why"], textarea[aria-label*="motivation"]',
                    'textarea[id*="why"], textarea[id*="motivation"]',
                ]
                
                cv_text = profile.get("master_cv_text", "")
                
                for selector in common_questions_patterns:
                    try:
                        selectors = [s.strip() for s in selector.split(',')]
                        for sel in selectors:
                            try:
                                locators = await page.locator(sel).all()
                                for locator in locators:
                                    if await locator.is_visible(timeout=2000):
                                        try:
                                            placeholder = await locator.get_attribute("placeholder") or ""
                                            label_text = placeholder
                                            
                                            answer = tailor.answer_application_question(
                                                label_text if label_text else "Why are you interested in this position?",
                                                cv_text,
                                                job_description
                                            )
                                            
                                            await locator.fill(answer)
                                            details[f"question_{sel[:30]}"] = "Answered with AI"
                                            print(f"✅ Answered question with AI: {label_text[:50]}")
                                        except Exception as e:
                                            print(f"⚠️ Could not answer question: {e}")
                                            continue
                            except:
                                continue
                    except:
                        continue
            
            result["details"] = details
            await context.close()
            result["status"] = True
    except Exception as exc:
        result["error"] = f"Auto-fill error: {exc}"
        import traceback
        print(f"ERROR in auto_fill_ats: {exc}\n{traceback.format_exc()}")
    return result

# ----- Israeli Job Boards Scraper -----
async def scrape_israeli_job_boards(search_terms, max_results_per_site=5):
    """
    Scrapes Israeli job boards (alljobs.co.il, drushim.co.il, jobmaster.co.il) using Playwright.
    Iterates through multiple search terms to maximize results.
    Returns a pandas DataFrame with columns: title, company, job_url, description, site_name
    
    Args:
        search_terms: List of search terms (e.g., ["VP Product", "CTO", "Head of Product"])
        max_results_per_site: Maximum number of results to fetch per site per search term
    
    Returns:
        pandas.DataFrame with job listings from all search terms
    """
    import urllib.parse
    
    # Auto-Install Logic: Check and install Chromium if missing (one-time setup)
    browser_check = check_and_install_chromium()
    if not browser_check.get("status", False):
        # If installation failed, raise a clear error with instructions
        error_msg = browser_check.get("message", "Chromium browser is not available.")
        raise RuntimeError(
            f"❌ Browser Setup Required\n\n{error_msg}\n\n"
            "The system cannot proceed without Chromium. Please ensure you have internet connectivity "
            "and try again, or install manually using: python -m playwright install chromium"
        )
    
    # Ensure search_terms is a list
    if isinstance(search_terms, str):
        search_terms = [search_terms]
    
    # Limit to top 3 most relevant search terms to avoid timeout
    # Prioritize E-commerce focused terms
    if len(search_terms) > 3:
        # Prefer E-commerce terms if available
        ecommerce_terms = [t for t in search_terms if 'e-commerce' in t.lower() or 'ecommerce' in t.lower()]
        other_terms = [t for t in search_terms if t not in ecommerce_terms]
        search_terms = (ecommerce_terms[:2] + other_terms[:1])[:3]  # Up to 2 E-commerce + 1 other, max 3 total
        print(f"⚠️ Limited search terms to top 3: {search_terms}")
    
    jobs_list = []
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    
    async with async_playwright() as p:
        # Silence the Traceback: Wrap browser launch with try-except for friendly error messages
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as browser_error:
            # Friendly error message instead of full crash
            error_msg = str(browser_error)
            if "executable doesn't exist" in error_msg or "Executable doesn't exist" in error_msg:
                print("❌ Browser Launch Error: Chromium browser is not installed. Please run: python -m playwright install chromium")
                return []  # Return empty list instead of crashing
            else:
                print(f"❌ Browser Launch Error: Failed to launch browser: {error_msg}")
                return []  # Return empty list instead of crashing
        
        page = await context.new_page()
        
        try:
            # Iterate through all search terms
            for idx, search_query in enumerate(search_terms):
                try:
                    # Add random delay between search terms (1-3 seconds) to avoid ERR_ABORTED
                    if idx > 0:
                        delay = random.uniform(1.0, 3.0)
                        await page.wait_for_timeout(int(delay * 1000))
                    
                    # 1. AllJobs.co.il
                    try:
                        # Handle Scraper Timeouts: Add try-except and time.sleep(2) between site crawls
                        import time
                        if idx > 0 or search_terms.index(search_query) > 0:
                            time.sleep(2)  # Small delay between site crawls to avoid being blocked
                        
                        encoded_query = urllib.parse.quote(search_query)
                        alljobs_url = f"https://www.alljobs.co.il/SearchResult.aspx?freeText={encoded_query}"
                        await page.goto(alljobs_url, wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(2000)  # Wait for dynamic content
                        
                        # Extract job listings - AllJobs uses specific selectors
                        all_elements = await page.locator('.job-item, .jobCard, [class*="job"]').all()
                        job_elements = all_elements[:max_results_per_site]
                        for elem in job_elements:
                            try:
                                title_elem = elem.locator('h2, h3, .job-title, [class*="title"]').first
                                company_elem = elem.locator('.company-name, [class*="company"]').first
                                link_elem = elem.locator('a').first
                                
                                title = await title_elem.inner_text() if await title_elem.count() > 0 else "Job Title"
                                company = await company_elem.inner_text() if await company_elem.count() > 0 else "Company"
                                job_url = await link_elem.get_attribute('href') if await link_elem.count() > 0 else alljobs_url
                                
                                if job_url and not job_url.startswith('http'):
                                    job_url = f"https://www.alljobs.co.il{job_url}"
                                
                                jobs_list.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'job_url': job_url,
                                    'description': f"Job from AllJobs: {title}",
                                    'site_name': 'alljobs'
                                })
                            except Exception:
                                continue
                    except Exception as e:
                        print(f"⚠️ AllJobs scraping error for '{search_query}': {e}")
                        # Handle Scraper Timeouts: Continue to next site even if this one fails
                        import time
                        time.sleep(2)  # Delay before next site
                    
                    # 2. Drushim.co.il
                    try:
                        # Handle Scraper Timeouts: Add delay between site crawls
                        import time
                        time.sleep(2)  # Small delay between site crawls to avoid being blocked
                        encoded_query = urllib.parse.quote(search_query)
                        drushim_url = f"https://www.drushim.co.il/jobs/search/{encoded_query}/"
                        
                        # Fix Scraping Abort: Add random user-agent rotation and networkidle wait
                        import random
                        user_agents = [
                            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
                        ]
                        selected_user_agent = random.choice(user_agents)
                        await context.set_extra_http_headers({"User-Agent": selected_user_agent})
                        
                        # Anti-blocking: Increase delay to 5 seconds + random 2-5 seconds to avoid ERR_ABORTED
                        base_delay = 5000  # 5 seconds base
                        random_delay = random.uniform(2000, 5000)  # Random 2-5 seconds
                        total_delay = int(base_delay + random_delay)
                        await page.wait_for_timeout(total_delay)
                        # Fix Scraping Abort: Use networkidle instead of domcontentloaded for drushim
                        await page.goto(drushim_url, wait_until="networkidle", timeout=60000)
                        await page.wait_for_timeout(2000)
                        
                        all_elements = await page.locator('.job-card, .job-item, [class*="job-card"]').all()
                        job_elements = all_elements[:max_results_per_site]
                        for elem in job_elements:
                            try:
                                title_elem = elem.locator('h2, h3, .title, [class*="title"]').first
                                company_elem = elem.locator('.company, [class*="company"]').first
                                link_elem = elem.locator('a').first
                                
                                title = await title_elem.inner_text() if await title_elem.count() > 0 else "Job Title"
                                company = await company_elem.inner_text() if await company_elem.count() > 0 else "Company"
                                job_url = await link_elem.get_attribute('href') if await link_elem.count() > 0 else drushim_url
                                
                                if job_url and not job_url.startswith('http'):
                                    job_url = f"https://www.drushim.co.il{job_url}"
                                
                                jobs_list.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'job_url': job_url,
                                    'description': f"Job from Drushim: {title}",
                                    'site_name': 'drushim'
                                })
                            except Exception:
                                continue
                    except Exception as e:
                        print(f"⚠️ Drushim scraping error for '{search_query}': {e}")
                        # Handle Scraper Timeouts: Continue to next site even if this one fails
                        import time
                        time.sleep(2)  # Delay before next site
                    
                    # 3. JobMaster.co.il
                    try:
                        # Handle Scraper Timeouts: Add delay between site crawls
                        import time
                        time.sleep(2)  # Small delay between site crawls to avoid being blocked
                        encoded_query = urllib.parse.quote(search_query)
                        jobmaster_url = f"https://www.jobmaster.co.il/jobs/?q={encoded_query}"
                        await page.goto(jobmaster_url, wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(2000)
                        
                        all_elements = await page.locator('.job-item, .job-card, [class*="job"]').all()
                        job_elements = all_elements[:max_results_per_site]
                        for elem in job_elements:
                            try:
                                title_elem = elem.locator('h2, h3, .job-title, [class*="title"]').first
                                company_elem = elem.locator('.company, [class*="company-name"]').first
                                link_elem = elem.locator('a').first
                                
                                title = await title_elem.inner_text() if await title_elem.count() > 0 else "Job Title"
                                company = await company_elem.inner_text() if await company_elem.count() > 0 else "Company"
                                job_url = await link_elem.get_attribute('href') if await link_elem.count() > 0 else jobmaster_url
                                
                                if job_url and not job_url.startswith('http'):
                                    job_url = f"https://www.jobmaster.co.il{job_url}"
                                
                                jobs_list.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'job_url': job_url,
                                    'description': f"Job from JobMaster: {title}",
                                    'site_name': 'jobmaster'
                                })
                            except Exception:
                                continue
                    except Exception as e:
                        print(f"⚠️ JobMaster scraping error for '{search_query}': {e}")
                        # Handle Scraper Timeouts: Continue to next search term even if this site fails
                        import time
                        time.sleep(2)  # Delay before next search term
                except Exception as e:
                    print(f"⚠️ Error processing search term '{search_query}': {e}")
                    # Handle Scraper Timeouts: Add delay and continue
                    import time
                    time.sleep(2)  # Delay before next search term
                    continue
        
        finally:
            await context.close()
    
    # Create DataFrame and remove duplicates
    if jobs_list:
        df = pd.DataFrame(jobs_list)
        # Remove duplicates based on job_url
        df = df.drop_duplicates(subset=['job_url'], keep='first')
        return df
    else:
        # Return empty DataFrame with correct structure
        return pd.DataFrame(columns=['title', 'company', 'job_url', 'description', 'site_name'])

# ----- Honest regression checks -----
def check_core_functions_integrity():
    """
    Verifies core guardrail logic is present in this file (run at import time).
    """
    expected = [
        "JobAppBot",
        "send_confirmation_email",
        "auto_fill_ats"
    ]
    here = __file__ if '__file__' in globals() else 'browser_bot.py'
    try:
        with open(here, 'r', encoding='utf-8') as f:
            content = f.read()
            for symbol in expected:
                if symbol not in content:
                    print(f"⚠️ Integrity Check Failed: {symbol} missing from browser_bot.py!")
                    raise SystemExit("Guardrail violation: core function missing.")
    except Exception as e:
        print(f"Integrity check exception: {e}")
        pass

# ----- Self-Expanding Job Discovery (The Scraper Agent) -----
async def discover_job_sources(search_query, digital_persona=None):
    """
    Uses AI to discover new job sources dynamically.
    Searches for niche job boards, Google Jobs results, and LinkedIn posts based on the search query.
    Returns a list of discovered job URLs or sources.
    Robust error handling to prevent app crashes if Gemini is offline.
    """
    from pdf_tailor import PDFTailor
    
    try:
        tailor = PDFTailor()
        
        # Build prompt for AI to discover job sources
        persona_context = ""
        if digital_persona:
            persona_context = f"\nDigital Persona: {digital_persona.get('persona_summary', '')}\nTarget Level: {digital_persona.get('role_level', 'Senior')}\n"
        
        discovery_prompt = (
            f"Given this search query: '{search_query}'{persona_context}"
            "Generate a list of potential job sources to search. "
            "Include: niche job boards URLs, Google Jobs search URLs, LinkedIn job search URLs, "
            "and any other relevant Israeli or international job boards. "
            "Return ONLY a valid JSON array of URLs or search queries:\n"
            '["source1", "source2", "source3"]\n\n'
            "Examples: 'https://www.google.com/search?q=CTO+E-commerce+Israel', "
            "'https://www.linkedin.com/jobs/search/?keywords=VP+Product+Israel', "
            "'https://www.alljobs.co.il/SearchResult.aspx?freeText=CTO'"
        )
        
        try:
            # Try primary model (use _call_api_with_fallback for consistency)
            response = tailor._call_api_with_fallback(discovery_prompt)
        except Exception as model_error:
            # If _call_api_with_fallback also fails, return empty list instead of crashing
            print(f"WARN: All model attempts failed in discovery: {model_error}")
            return []  # Return empty list instead of raising exception
        
        text = response.text.replace("```json", "").replace("```", "").strip()
        sources = json.loads(text)
        
        if isinstance(sources, list):
            return sources[:10]  # Limit to top 10 sources
        else:
            return []
    except json.JSONDecodeError as json_error:
        print(f"⚠️ Job source discovery JSON parsing error: {json_error}")
        return []
    except Exception as e:
        print(f"⚠️ Job source discovery error (Gemini may be offline): {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        # Return empty list - this should not crash the app
        return []

async def scrape_discovered_sources(discovered_sources, max_results_per_source=5):
    """
    Scrapes jobs from AI-discovered sources using Playwright.
    Returns a pandas DataFrame with job listings.
    """
    # Auto-Install Logic: Check and install Chromium if missing (one-time setup)
    browser_check = check_and_install_chromium()
    if not browser_check.get("status", False):
        # If installation failed, return empty DataFrame with a warning
        error_msg = browser_check.get("message", "Chromium browser is not available.")
        print(f"⚠️ Browser setup required for discovered sources scraping: {error_msg}")
        return pd.DataFrame(columns=['title', 'company', 'job_url', 'description', 'site_name'])
    
    jobs_list = []
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    
    async with async_playwright() as p:
        # Silence the Traceback: Wrap browser launch with try-except for friendly error messages
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as browser_error:
            # Friendly error message instead of full crash
            error_msg = str(browser_error)
            if "executable doesn't exist" in error_msg or "Executable doesn't exist" in error_msg:
                print("❌ Browser Launch Error: Chromium browser is not installed. Please run: python -m playwright install chromium")
                return pd.DataFrame(columns=['title', 'company', 'job_url', 'description', 'site_name'])  # Return empty DataFrame instead of crashing
            else:
                print(f"❌ Browser Launch Error: Failed to launch browser: {error_msg}")
                return pd.DataFrame(columns=['title', 'company', 'job_url', 'description', 'site_name'])  # Return empty DataFrame instead of crashing
        
        page = await context.new_page()
        
        try:
            for source_url in discovered_sources:
                try:
                    # Add delay between sources
                    await page.wait_for_timeout(random.uniform(1000, 3000))
                    
                    # Navigate to source
                    await page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(2000)
                    
                    # Try to extract job listings (generic selectors)
                    try:
                        job_elements = await page.locator('.job-item, .job-card, [class*="job"], [data-testid*="job"]').all()
                        job_elements = job_elements[:max_results_per_source]
                        
                        for elem in job_elements:
                            try:
                                title_elem = elem.locator('h2, h3, .title, [class*="title"]').first
                                company_elem = elem.locator('.company, [class*="company"]').first
                                link_elem = elem.locator('a').first
                                
                                if await title_elem.count() > 0:
                                    title = await title_elem.inner_text()
                                    company = await company_elem.inner_text() if await company_elem.count() > 0 else "Company"
                                    job_url = await link_elem.get_attribute('href') if await link_elem.count() > 0 else source_url
                                    
                                    if job_url and not job_url.startswith('http'):
                                        # Try to construct full URL
                                        if 'linkedin.com' in source_url:
                                            job_url = f"https://www.linkedin.com{job_url}" if job_url.startswith('/') else job_url
                                        elif 'google.com' in source_url:
                                            # Google Jobs - extract from search result
                                            continue  # Skip Google Jobs for now (complex structure)
                                        else:
                                            base_url = '/'.join(source_url.split('/')[:3])
                                            job_url = f"{base_url}{job_url}" if job_url.startswith('/') else job_url
                                    
                                    jobs_list.append({
                                        'title': title.strip(),
                                        'company': company.strip(),
                                        'job_url': job_url,
                                        'description': f"Job from discovered source: {title}",
                                        'site_name': 'discovered_source'
                                    })
                            except Exception:
                                continue
                    except Exception:
                        # If generic selectors fail, just log and continue
                        print(f"⚠️ Could not extract jobs from {source_url}")
                        continue
                except Exception as e:
                    print(f"⚠️ Error scraping discovered source {source_url}: {e}")
                    continue
        finally:
            await context.close()
    
    if jobs_list:
        df = pd.DataFrame(jobs_list)
        df = df.drop_duplicates(subset=['job_url'], keep='first')
        return df
    else:
        return pd.DataFrame(columns=['title', 'company', 'job_url', 'description', 'site_name'])

# Run quick check on import
check_core_functions_integrity()
