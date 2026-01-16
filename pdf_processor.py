import fitz  # PyMuPDF

class PDFParser:
    def extract_text(self, pdf_path):
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            return text
        except Exception as e:
            return f"Error reading PDF: {str(e)}"