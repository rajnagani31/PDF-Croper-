from utils import remove_pdf_whitespace , extract_meesho_data, create_order_summary, create_courier_summary, create_company_summary, create_pdf_report
import fitz

# PDF Processor Utility Functions

def process_pdf(input_pdf ,filter):
    original = fitz.open(stream=input_pdf, filetype="pdf")
    final_doc = fitz.open()

    

    if filter['remove_white']:
        pdf = remove_pdf_whitespace(original)
        final_doc.insert_pdf(pdf)
    else:
        final_doc.insert_pdf(original)

    if filter['print_datetime']:
        pass 


    if filter['bottom_of_the_table']:
            # Extract data and create summary tables
            extracted_data = extract_meesho_data(original)
            
            if extracted_data:  # Only create summary if data found
                order_summary = create_order_summary(extracted_data)
                courier_summary = create_courier_summary(extracted_data)
                company_summary = create_company_summary(extracted_data)
                
                # Generate summary PDF
                summary_pdf_buffer = create_pdf_report(order_summary, courier_summary, company_summary)
                summary_doc = fitz.open(stream=summary_pdf_buffer, filetype="pdf")
                
                # Add summary pages at the end
                final_doc.insert_pdf(summary_doc)

    
    return final_doc