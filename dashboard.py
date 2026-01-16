import streamlit as st
import os

# ייבוא ישיר ופשוט - ללא נקודות וללא utils
try:
    import llm_client
    import pdf_processor
    
    # יצירת קיצורי דרך למחלקות
    LLMClient = llm_client.LLMClient
    PDFProcessor = pdf_processor.PDFProcessor
except Exception as e:
    st.error(f"שגיאת ייבוא: המערכת לא מוצאת את הקבצים llm_client.py או pdf_processor.py בתיקייה הראשית.")
    st.info(f"פרטי השגיאה: {e}")

st.set_page_config(page_title="AI Resume Analyzer", layout="wide")

def main():
    st.title("📄 מנתח קורות חיים (Gemini 1.5 Flash)")
    
    if 'llm' not in st.session_state:
        try:
            st.session_state.llm = LLMClient()
        except NameError:
            return # השגיאה כבר תוצג למעלה

    uploaded_file = st.file_uploader("העלה קובץ PDF", type=['pdf'])

    if uploaded_file and st.button("בצע ניתוח"):
        with st.spinner("מנתח..."):
            try:
                proc = PDFProcessor()
                text = proc.extract_text(uploaded_file)
                if text:
                    res = st.session_state.llm.ask(text, "Extract skills and experience.")
                    st.info(res)
                    st.balloons()
                else:
                    st.error("לא חולץ טקסט מהקובץ.")
            except Exception as e:
                st.error(f"שגיאה: {e}")

if __name__ == "__main__":
    main()