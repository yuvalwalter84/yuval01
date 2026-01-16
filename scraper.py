import asyncio
from crawl4ai import AsyncWebCrawler

async def search_jobs(job_title, location="Israel"):
    # בניית URL לחיפוש (דוגמה ל-Indeed או LinkedIn)
    search_url = f"https://www.linkedin.com/jobs/search/?keywords={job_title}&location={location}"
    
    async with AsyncWebCrawler(verbose=True) as crawler:
        result = await crawler.arun(url=search_url)
        # כאן נכנסת הלוגיקה של חילוץ המשרות מה-Markdown ש-Crawl4AI מחזיר
        return result.markdown

# פונקציית עזר להרצה
if __name__ == "__main__":
    jobs = asyncio.run(search_jobs("Python Developer"))
    print(jobs[:500]) # הדפסת תצוגה מקדימה