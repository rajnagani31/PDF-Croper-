from utils import remove_pdf_whitespace, merge_pdfs, get_indian_datetime, print_datetime_on_label,process_pdf
import fitz

# PDF Processor Utility Functions

def process_pdf(input_pdf ,settings):
    original = fitz.open(stream=input_pdf, filetype="pdf")
    final_doc = fitz.open()

    page = None
    if settings['remove_white']:
        page = remove_pdf_whitespace(original)

        final_doc.insert_pdf(page)
    else:
        final_doc.insert_pdf(original)
    print("1")
    return final_doc