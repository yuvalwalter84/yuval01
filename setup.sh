#!/bin/bash
# Setup script for Job Search Agent

echo "Setting up AI Job Search Agent..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "Please edit .env and add your GEMINI_API_KEY"
else
    echo ".env file already exists"
fi

# Create output directory
mkdir -p output

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your GEMINI_API_KEY"
echo "2. Run: python main.py search path/to/your/resume.pdf"
