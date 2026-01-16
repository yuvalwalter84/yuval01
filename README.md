# AI Job Search Agent (Expert Level)

A powerful CLI and web-based AI-powered job search agent that analyzes your resume, searches for relevant jobs, matches them with your profile, and generates tailored application materials.

## Features

### Core Features
- **Resume Parser**: Extracts and analyzes PDF resumes using LLM to identify tech stack, experience, and seniority
- **Web Scraper**: Searches LinkedIn and Indeed with advanced bot detection bypass
- **Smart Matching**: Semantic similarity scoring and comprehensive gap analysis
- **Document Tailoring**: Generates customized resume summaries and cover letters
- **Multiple Output Formats**: CSV, Markdown, and JSON exports

### Expert-Level Enhancements
- **Advanced Gap Analysis**: Identifies missing skills AND bonus skills you have
- **Seniority Matching**: Intelligent seniority level matching with penalty system
- **Match Explanations**: AI-generated explanations for "Why this is a good fit" and "Biggest hurdle"
- **CV Optimization Suggestions**: 3 specific, actionable suggestions to modify your CV for each job
- **LinkedIn Cold Outreach**: Personalized LinkedIn messages (under 300 characters) for recruiters
- **Enhanced Stealth Scraping**: Rotating user agents, random delays (1-5 seconds), CAPTCHA detection
- **Status Tracking**: Logs failed scrapes with reasons (CAPTCHA, 404, Timeout, etc.) for retry
- **Interactive Dashboard**: Streamlit web interface with CV upload, searchable results, and download features
- **JSON Logging**: Detailed JSON reports for every job analyzed in `logs/` directory

## Installation

1. Clone the repository:
```bash
cd /home/yuvalwalter/yuval01
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

## Configuration

Edit `.env` file with your API keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
LLM_PROVIDER=gemini
LLM_MODEL=gemini/gemini-1.5-flash
```

You can also use other providers:
- Groq: Set `LLM_PROVIDER=groq` and `LLM_MODEL=groq/llama-3.1-70b-versatile`
- OpenAI: Set `LLM_PROVIDER=openai` and `LLM_MODEL=gpt-4`

## Usage

### Search for Jobs

```bash
python main.py search path/to/resume.pdf --location "San Francisco, CA" --max-results 30
```

Options:
- `--location, -l`: Job search location (optional)
- `--sources, -s`: Comma-separated sources (linkedin,indeed). Default: "linkedin,indeed"
- `--max-results, -m`: Maximum results per source. Default: 20
- `--generate-docs/--no-generate-docs`: Generate tailored documents. Default: True
- `--top-n, -n`: Number of top matches to generate documents for. Default: 5
- `--format, -f`: Output format (csv, md, both). Default: both

### Analyze Resume Only

```bash
python main.py analyze path/to/resume.pdf
```

### Interactive Dashboard

Launch the Streamlit dashboard for a web-based interface:

```bash
streamlit run dashboard.py
```

The dashboard provides:
- Resume upload and analysis
- Interactive job search
- Searchable results table with filters
- Match score visualization
- Gap analysis display
- One-click generation of tailored materials
- Download buttons for all documents

## Output

Results are saved to the `output/` directory:

- `jobs_tracker.csv`: Spreadsheet with all matched jobs
- `jobs_tracker.md`: Markdown table with results
- `[Company]_[JobTitle]_summary.txt`: Tailored resume summaries
- `[Company]_[JobTitle]_cover_letter.txt`: Tailored cover letters

### JSON Logs

Detailed analysis logs are saved to the `logs/` directory:

- `[Company]_[JobTitle]_[timestamp].json`: Complete job analysis including:
  - Match score breakdown
  - Missing and bonus skills
  - Seniority matching details
  - Good fit and hurdle explanations
  - Resume summary data

### Enhanced Job Matching Output

Each matched job now includes:
- **Match Score** (0-100): Overall compatibility score
- **Missing Skills**: Skills required but not in your resume
- **Bonus Skills**: Skills you have that are valuable but not required
- **Seniority Match**: Analysis of level alignment with penalty/adjustment
- **Good Fit Explanation**: Why this job is a good match (1-2 sentences)
- **Biggest Hurdle**: Main challenge to address (1-2 sentences)
- **Gaps**: List of identified gaps (technologies, experience, education)

### Tailored Materials

For each job, you can generate:
1. **Tailored Resume Summary**: Customized 2-3 sentence summary
2. **Cover Letter**: Professional cover letter addressing gaps
3. **CV Modification Suggestions**: 3 specific, actionable suggestions
4. **LinkedIn Cold Outreach**: Personalized message under 300 characters

## Project Structure

```
yuval01/
├── main.py                 # CLI interface
├── dashboard.py           # Streamlit web dashboard
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── modules/
│   ├── resume_parser.py   # PDF parsing and analysis
│   ├── web_scraper.py     # Enhanced job scraping with stealth mode
│   ├── job_matcher.py     # Advanced matching with gap analysis
│   ├── tailoring.py       # Document generation + CV suggestions + LinkedIn
│   └── output_manager.py  # CSV/Markdown export
├── utils/
│   └── llm_client.py      # LiteLLM client (optimized for Gemini 1.5 Flash)
├── output/                # Generated files (CSV, MD, tailored documents)
└── logs/                  # JSON analysis logs
```

## How It Works

1. **Resume Parsing**: Extracts text from PDF and uses LLM to identify:
   - Tech stack
   - Years of experience
   - Seniority level
   - Job titles

2. **Job Search**: Searches LinkedIn and Indeed using job titles from resume

3. **Matching**: For each job:
   - Calculates semantic similarity score (sentence-transformers)
   - Performs keyword matching
   - Analyzes missing skills vs. bonus skills
   - Checks seniority level alignment (with penalty system)
   - Generates match explanations (good fit + biggest hurdle)
   - Generates overall match score (0-100)

4. **Tailoring**: For top matches:
   - Generates customized resume summary
   - Creates tailored cover letter addressing gaps
   - Provides 3 specific CV modification suggestions
   - Generates LinkedIn cold outreach message

5. **Export**: Saves results to CSV, Markdown, and JSON formats
6. **Logging**: Creates detailed JSON logs for each job analysis in `logs/` directory

## Error Handling & Status Tracking

The agent includes comprehensive error handling:
- Retry logic for web scraping (exponential backoff)
- Fallback PDF extraction methods (PyMuPDF → pdfplumber)
- Graceful degradation if LLM calls fail
- Detailed logging to `job_search_agent.log`
- **Status Tracking**: Failed scrapes are logged with reasons:
  - CAPTCHA detected
  - 404 Not Found
  - Timeout errors
  - Other errors (with truncated messages)
- Failed scrapes can be retrieved via `web_scraper.get_failed_scrapes()`

## Technical Details

### LLM Optimization
- Optimized for **Gemini 1.5 Flash** (high speed, low cost)
- All LLM calls use `llm_client.py` for easy model switching
- Temperature and token limits optimized for quality and speed

### Stealth Scraping
- **Rotating User Agents**: 7 different user agents rotated automatically
- **Random Delays**: 1-5 second delays between requests (human-like)
- **CAPTCHA Detection**: Automatically detects and logs CAPTCHA challenges
- **Error Tracking**: All failures logged with timestamps and reasons

### Seniority Matching
The system uses a 5-level seniority mapping:
- Junior (1) → Mid (2) → Senior (3) → Lead (4) → Principal (5)

Penalties applied:
- Major mismatch (2+ levels): -15 points
- Minor gap (1 level): -5 points
- Overqualified (2+ levels above): -10 points
- Perfect match: +5 points bonus

## Notes

- Web scraping may be rate-limited by job sites
- Some job descriptions may not be fully accessible
- Match scores are estimates based on semantic similarity and keyword matching
- Always review generated documents before submitting
- LinkedIn messages are kept under 300 characters for optimal engagement
- Failed scrapes are logged for manual review and retry

## License

MIT
