"""Web scraper module for LinkedIn and Indeed job searches."""
import logging
import time
import random
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from config import Config
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class WebScraper:
    """Web scraper for job search sites with bot detection bypass."""
    
    def __init__(self):
        """Initialize web scraper."""
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        ]
        self.current_user_agent_index = 0
        self.failed_scrapes = []  # Track failed scrapes with reasons
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent (rotating through list)."""
        # Rotate through user agents
        user_agent = self.user_agents[self.current_user_agent_index]
        self.current_user_agent_index = (self.current_user_agent_index + 1) % len(self.user_agents)
        return user_agent
    
    def _human_delay(self, min_seconds: float = 1.0, max_seconds: float = 5.0) -> None:
        """Add human-like random delay between requests.
        
        Args:
            min_seconds: Minimum delay in seconds (default 1)
            max_seconds: Maximum delay in seconds (default 5)
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _log_failed_scrape(self, job_title: str, source: str, reason: str, url: str = "") -> None:
        """Log a failed scrape attempt with reason.
        
        Args:
            job_title: Job title that failed
            source: Source (linkedin/indeed)
            reason: Failure reason (Captcha, 404, Timeout, etc.)
            url: Optional URL that failed
        """
        failure = {
            "job_title": job_title,
            "source": source,
            "reason": reason,
            "url": url,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.failed_scrapes.append(failure)
        logger.warning(f"Failed scrape: {job_title} from {source} - {reason}")
    
    def get_failed_scrapes(self) -> List[Dict[str, str]]:
        """Get list of failed scrapes with reasons.
        
        Returns:
            List of failed scrape dictionaries
        """
        return self.failed_scrapes.copy()
    
    def start_browser(self) -> None:
        """Start browser instance."""
        if self.browser is None:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=Config.SCRAPER_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            )
            logger.info("Browser started")
    
    def close_browser(self) -> None:
        """Close browser instance."""
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        logger.info("Browser closed")
    
    def _create_stealth_page(self) -> Page:
        """Create a page with stealth settings to bypass bot detection."""
        context = self.browser.new_context(
            user_agent=self._get_random_user_agent(),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York"
        )
        
        page = context.new_page()
        
        # Remove webdriver property
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # Override permissions
        page.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        return page
    
    def _detect_captcha(self, page: Page) -> bool:
        """Detect if page shows a CAPTCHA.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if CAPTCHA detected
        """
        try:
            # Check for common CAPTCHA indicators
            captcha_indicators = [
                "captcha",
                "verify you're human",
                "challenge",
                "security check"
            ]
            page_text = page.content().lower()
            return any(indicator in page_text for indicator in captcha_indicators)
        except:
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def scrape_linkedin(self, job_titles: List[str], location: str = "", max_results: int = 20) -> List[Dict[str, str]]:
        """Scrape LinkedIn for jobs.
        
        Args:
            job_titles: List of job titles to search for
            location: Location filter (optional)
            max_results: Maximum number of jobs to return
            
        Returns:
            List of job dictionaries with title, company, description, link
        """
        if self.browser is None:
            self.start_browser()
        
        jobs = []
        
        for job_title in job_titles:
            try:
                logger.info(f"Searching LinkedIn for: {job_title}")
                page = self._create_stealth_page()
                
                # Construct search URL
                search_query = f"{job_title} {location}".strip()
                url = f"https://www.linkedin.com/jobs/search/?keywords={search_query.replace(' ', '%20')}"
                
                page.goto(url, wait_until="networkidle", timeout=Config.SCRAPER_TIMEOUT * 1000)
                
                # Check for CAPTCHA
                if self._detect_captcha(page):
                    self._log_failed_scrape(job_title, "LinkedIn", "CAPTCHA detected", url)
                    page.close()
                    self._human_delay(1, 5)
                    continue
                
                # Check for 404 or error pages
                if "404" in page.url or "error" in page.url.lower():
                    self._log_failed_scrape(job_title, "LinkedIn", "404 Not Found", url)
                    page.close()
                    self._human_delay(1, 5)
                    continue
                
                self._human_delay(1, 5)  # Random delay 1-5 seconds
                
                # Scroll to load more results
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self._human_delay(1, 5)
                
                # Extract job listings
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                
                # LinkedIn job listing selectors (may need adjustment based on current structure)
                job_cards = soup.find_all("div", class_="job-search-card") or \
                           soup.find_all("li", class_="jobs-search-results__list-item")
                
                for card in job_cards[:max_results]:
                    try:
                        title_elem = card.find("a", class_="job-search-card__title-link") or \
                                    card.find("h3", class_="base-search-card__title")
                        company_elem = card.find("a", class_="job-search-card__subtitle-link") or \
                                      card.find("h4", class_="base-search-card__subtitle")
                        link_elem = card.find("a", href=True)
                        
                        if title_elem and link_elem:
                            job = {
                                "title": title_elem.get_text(strip=True),
                                "company": company_elem.get_text(strip=True) if company_elem else "Unknown",
                                "link": link_elem.get("href", ""),
                                "description": "",  # Will be filled when clicking job
                                "source": "LinkedIn"
                            }
                            
                            # Try to get full description
                            try:
                                if not job["link"].startswith("http"):
                                    job["link"] = f"https://www.linkedin.com{job['link']}"
                                
                                page.goto(job["link"], wait_until="networkidle", timeout=10000)
                                self._human_delay()
                                
                                desc_html = page.content()
                                desc_soup = BeautifulSoup(desc_html, "html.parser")
                                desc_elem = desc_soup.find("div", class_="show-more-less-html__markup") or \
                                           desc_soup.find("div", class_="description__text")
                                
                                if desc_elem:
                                    job["description"] = desc_elem.get_text(strip=True)
                            except Exception as e:
                                logger.warning(f"Could not fetch full description: {e}")
                            
                            jobs.append(job)
                            if len(jobs) >= max_results:
                                break
                    
                    except Exception as e:
                        logger.warning(f"Error parsing job card: {e}")
                        continue
                
                page.close()
                self._human_delay(1, 5)
            
            except PlaywrightTimeout:
                self._log_failed_scrape(job_title, "LinkedIn", "Timeout", url if 'url' in locals() else "")
                continue
            except Exception as e:
                error_msg = str(e)[:100]  # Truncate long error messages
                self._log_failed_scrape(job_title, "LinkedIn", f"Error: {error_msg}", url if 'url' in locals() else "")
                continue
        
        logger.info(f"Found {len(jobs)} jobs from LinkedIn")
        return jobs[:max_results]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def scrape_indeed(self, job_titles: List[str], location: str = "", max_results: int = 20) -> List[Dict[str, str]]:
        """Scrape Indeed for jobs.
        
        Args:
            job_titles: List of job titles to search for
            location: Location filter (optional)
            max_results: Maximum number of jobs to return
            
        Returns:
            List of job dictionaries with title, company, description, link
        """
        if self.browser is None:
            self.start_browser()
        
        jobs = []
        
        for job_title in job_titles:
            try:
                logger.info(f"Searching Indeed for: {job_title}")
                page = self._create_stealth_page()
                
                # Construct search URL
                search_query = f"{job_title} {location}".strip()
                url = f"https://www.indeed.com/jobs?q={search_query.replace(' ', '+')}&l={location.replace(' ', '+')}"
                
                page.goto(url, wait_until="networkidle", timeout=Config.SCRAPER_TIMEOUT * 1000)
                
                # Check for CAPTCHA
                if self._detect_captcha(page):
                    self._log_failed_scrape(job_title, "Indeed", "CAPTCHA detected", url)
                    page.close()
                    self._human_delay(1, 5)
                    continue
                
                # Check for 404 or error pages
                if "404" in page.url or "error" in page.url.lower():
                    self._log_failed_scrape(job_title, "Indeed", "404 Not Found", url)
                    page.close()
                    self._human_delay(1, 5)
                    continue
                
                self._human_delay(1, 5)  # Random delay 1-5 seconds
                
                # Scroll to load more results
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self._human_delay(1, 5)
                
                # Extract job listings
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                
                # Indeed job listing selectors
                job_cards = soup.find_all("div", class_="job_seen_beacon") or \
                           soup.find_all("td", class_="resultContent")
                
                for card in job_cards[:max_results]:
                    try:
                        title_elem = card.find("h2", class_="jobTitle") or \
                                    card.find("a", {"data-jk": True})
                        company_elem = card.find("span", class_="companyName")
                        link_elem = card.find("a", href=True)
                        
                        if title_elem and link_elem:
                            job = {
                                "title": title_elem.get_text(strip=True),
                                "company": company_elem.get_text(strip=True) if company_elem else "Unknown",
                                "link": link_elem.get("href", ""),
                                "description": "",
                                "source": "Indeed"
                            }
                            
                            # Ensure full URL
                            if job["link"].startswith("/"):
                                job["link"] = f"https://www.indeed.com{job['link']}"
                            
                            # Try to get full description
                            try:
                                page.goto(job["link"], wait_until="networkidle", timeout=10000)
                                self._human_delay()
                                
                                desc_html = page.content()
                                desc_soup = BeautifulSoup(desc_html, "html.parser")
                                desc_elem = desc_soup.find("div", id="jobDescriptionText") or \
                                           desc_soup.find("div", class_="jobsearch-jobDescriptionText")
                                
                                if desc_elem:
                                    job["description"] = desc_elem.get_text(strip=True)
                            except Exception as e:
                                logger.warning(f"Could not fetch full description: {e}")
                            
                            jobs.append(job)
                            if len(jobs) >= max_results:
                                break
                    
                    except Exception as e:
                        logger.warning(f"Error parsing job card: {e}")
                        continue
                
                page.close()
                self._human_delay(1, 5)
            
            except PlaywrightTimeout:
                self._log_failed_scrape(job_title, "Indeed", "Timeout", url if 'url' in locals() else "")
                continue
            except Exception as e:
                error_msg = str(e)[:100]
                self._log_failed_scrape(job_title, "Indeed", f"Error: {error_msg}", url if 'url' in locals() else "")
                continue
        
        logger.info(f"Found {len(jobs)} jobs from Indeed")
        return jobs[:max_results]
    
    def search_jobs(self, job_titles: List[str], location: str = "", sources: List[str] = None, max_results: int = 20) -> List[Dict[str, str]]:
        """Search for jobs across multiple sources.
        
        Args:
            job_titles: List of job titles to search for
            location: Location filter
            sources: List of sources to search (linkedin, indeed). Defaults to both
            max_results: Maximum results per source
            
        Returns:
            Combined list of jobs from all sources
        """
        if sources is None:
            sources = ["linkedin", "indeed"]
        
        all_jobs = []
        
        try:
            if "linkedin" in sources:
                linkedin_jobs = self.scrape_linkedin(job_titles, location, max_results)
                all_jobs.extend(linkedin_jobs)
            
            if "indeed" in sources:
                indeed_jobs = self.scrape_indeed(job_titles, location, max_results)
                all_jobs.extend(indeed_jobs)
        
        except Exception as e:
            logger.error(f"Error during job search: {e}")
        
        # Remove duplicates based on title and company
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            key = (job["title"].lower(), job["company"].lower())
            if key not in seen:
                seen.add(key)
                unique_jobs.append(job)
        
        logger.info(f"Total unique jobs found: {len(unique_jobs)}")
        return unique_jobs
