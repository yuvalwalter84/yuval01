"""Output manager for saving results to CSV and Markdown."""
import logging
import csv
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from config import Config

logger = logging.getLogger(__name__)


class OutputManager:
    """Manage output of job search results."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize output manager.
        
        Args:
            output_dir: Optional output directory. Defaults to Config.OUTPUT_DIR
        """
        self.output_dir = output_dir or Config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_to_csv(self, jobs: List[Dict[str, any]], filename: Optional[str] = None) -> Path:
        """Save job results to CSV file.
        
        Args:
            jobs: List of matched job dictionaries
            filename: Optional filename. Defaults to Config.JOBS_CSV_FILE
            
        Returns:
            Path to saved CSV file
        """
        if filename is None:
            filename = Config.JOBS_CSV_FILE
        
        csv_path = self.output_dir / filename
        
        if not jobs:
            logger.warning("No jobs to save")
            return csv_path
        
        # Prepare CSV data
        fieldnames = [
            "Job Title",
            "Company",
            "Match Score",
            "Gaps",
            "Link",
            "Source",
            "Location",
            "Date Added"
        ]
        
        rows = []
        for job in jobs:
            gaps_text = "; ".join(job.get("gaps", [])) if job.get("gaps") else "None"
            
            row = {
                "Job Title": job.get("title", ""),
                "Company": job.get("company", ""),
                "Match Score": f"{job.get('match_score', 0):.1f}%",
                "Gaps": gaps_text,
                "Link": job.get("link", ""),
                "Source": job.get("source", ""),
                "Location": job.get("location", ""),
                "Date Added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            rows.append(row)
        
        # Write CSV
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            logger.info(f"Saved {len(jobs)} jobs to {csv_path}")
            return csv_path
        
        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            raise
    
    def save_to_markdown(self, jobs: List[Dict[str, any]], filename: Optional[str] = None) -> Path:
        """Save job results to Markdown table.
        
        Args:
            jobs: List of matched job dictionaries
            filename: Optional filename. Defaults to 'jobs_tracker.md'
            
        Returns:
            Path to saved Markdown file
        """
        if filename is None:
            filename = "jobs_tracker.md"
        
        md_path = self.output_dir / filename
        
        if not jobs:
            logger.warning("No jobs to save")
            return md_path
        
        # Generate Markdown content
        md_content = f"# Job Search Results\n\n"
        md_content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md_content += f"Total Jobs: {len(jobs)}\n\n"
        md_content += "---\n\n"
        
        # Create table
        md_content += "| Job Title | Company | Match Score | Gaps | Link | Source |\n"
        md_content += "|-----------|---------|-------------|------|------|--------|\n"
        
        for job in jobs:
            title = job.get("title", "").replace("|", "\\|")
            company = job.get("company", "").replace("|", "\\|")
            score = f"{job.get('match_score', 0):.1f}%"
            gaps = "; ".join(job.get("gaps", []))[:100] if job.get("gaps") else "None"
            gaps = gaps.replace("|", "\\|")
            link = job.get("link", "")
            source = job.get("source", "")
            
            md_content += f"| {title} | {company} | {score} | {gaps} | [Link]({link}) | {source} |\n"
        
        # Add detailed sections for top matches
        md_content += "\n---\n\n"
        md_content += "## Top Matches\n\n"
        
        top_jobs = sorted(jobs, key=lambda x: x.get("match_score", 0), reverse=True)[:5]
        
        for i, job in enumerate(top_jobs, 1):
            md_content += f"### {i}. {job.get('title')} at {job.get('company')}\n\n"
            md_content += f"**Match Score:** {job.get('match_score', 0):.1f}%\n\n"
            md_content += f"**Link:** {job.get('link', '')}\n\n"
            
            if job.get("gaps"):
                md_content += "**Gaps Identified:**\n"
                for gap in job.get("gaps", []):
                    md_content += f"- {gap}\n"
                md_content += "\n"
            
            md_content += "---\n\n"
        
        # Write Markdown file
        try:
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            logger.info(f"Saved {len(jobs)} jobs to {md_path}")
            return md_path
        
        except Exception as e:
            logger.error(f"Error saving Markdown: {e}")
            raise
    
    def save_tailored_documents(
        self,
        job: Dict[str, any],
        resume_summary: str,
        cover_letter: str,
        filename_prefix: Optional[str] = None
    ) -> Dict[str, Path]:
        """Save tailored resume summary and cover letter for a job.
        
        Args:
            job: Job dictionary
            resume_summary: Tailored resume summary
            cover_letter: Tailored cover letter
            filename_prefix: Optional prefix for filenames
            
        Returns:
            Dictionary with paths to saved files
        """
        # Create safe filename from job title and company
        safe_title = "".join(c for c in job.get("title", "job") if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        safe_company = "".join(c for c in job.get("company", "company") if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        
        if filename_prefix:
            prefix = f"{filename_prefix}_"
        else:
            prefix = ""
        
        summary_path = self.output_dir / f"{prefix}{safe_company}_{safe_title}_summary.txt"
        cover_letter_path = self.output_dir / f"{prefix}{safe_company}_{safe_title}_cover_letter.txt"
        
        # Save resume summary
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"Tailored Resume Summary\n")
                f.write(f"{'='*50}\n\n")
                f.write(f"Job: {job.get('title')} at {job.get('company')}\n")
                f.write(f"Match Score: {job.get('match_score', 0):.1f}%\n")
                f.write(f"Link: {job.get('link', '')}\n\n")
                f.write(f"{'='*50}\n\n")
                f.write(resume_summary)
            
            logger.info(f"Saved resume summary to {summary_path}")
        
        except Exception as e:
            logger.error(f"Error saving resume summary: {e}")
            raise
        
        # Save cover letter
        try:
            with open(cover_letter_path, 'w', encoding='utf-8') as f:
                f.write(f"Tailored Cover Letter\n")
                f.write(f"{'='*50}\n\n")
                f.write(f"Job: {job.get('title')} at {job.get('company')}\n")
                f.write(f"Match Score: {job.get('match_score', 0):.1f}%\n")
                f.write(f"Link: {job.get('link', '')}\n\n")
                f.write(f"{'='*50}\n\n")
                f.write(cover_letter)
            
            logger.info(f"Saved cover letter to {cover_letter_path}")
        
        except Exception as e:
            logger.error(f"Error saving cover letter: {e}")
            raise
        
        return {
            "summary": summary_path,
            "cover_letter": cover_letter_path
        }
