# PDF CROPER API

from operator import le
import os
from fastapi import FastAPI , File, UploadFile,Form,Query,HTTPException 
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from utils import remove_pdf_whitespace, merge_pdfs, get_indian_datetime, print_datetime_on_label,process_pdf
from io import BytesIO
import fitz  # PyMuPDF
import zipfile
import datetime
import base64



app = FastAPI()

@app.post("/crop-pdf")
async def crop_pdf_editor(
    files: list[UploadFile] = File(...),
    merge: bool = Form(False),
    remove_white: bool = Form(False),
    print_datetime: bool = Form(False)
):
    try:
        settings = {
            "remove_white": remove_white,
            "print_datetime": print_datetime
        }

        # STEP 1: READ ALL PDFs INTO MEMORY
        input_pdf = []
        for file in files:
            file_bytes = await file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            input_pdf.append(doc)

        """ If merge is True then merge all PDF and apply process_pdf() on merged PDF and return single PDF""" 
        if merge:
            merged_doc = fitz.open()
            for pdf in input_pdf:
                merged_doc.insert_pdf(pdf)
        

            merged_bytes = BytesIO(merged_doc.tobytes())
            final_doc = process_pdf(merged_bytes, settings)

            return StreamingResponse(
                BytesIO(final_doc.tobytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=processed.pdf"}
            )
        
        """ If merge is False & and User pass one PDF then apply process_pdf() on each PDF and return zip of all processed PDFs"""
        if len(input_pdf) == 1:
            single_bytes = BytesIO(input_pdf[0].tobytes())
            final_doc = process_pdf(single_bytes, settings)

            return StreamingResponse(
                BytesIO(final_doc.tobytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=processed.pdf"}
            )


        """ If merge is False & and User pass multiple PDFs then apply process_pdf() on each PDF and return zip of all processed PDFs"""
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:

            for idx, pdf in enumerate(input_pdf):
                pdf_bytes = BytesIO(pdf.tobytes())
                processed_doc = process_pdf(pdf_bytes, settings)
                processed_bytes = processed_doc.tobytes()
                zip_file.writestr(f"processed_{idx + 1}.pdf", processed_bytes)

        zip_buffer.seek(0)
        print(zip_buffer)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=processed_pdfs.zip"}
        )

        # files_data = []

        # for idx, pdf_bytes in enumerate(input_pdf, start=1):

        #     processed_doc = process_pdf(pdf_bytes, settings)

        #     pdf_raw_bytes = processed_doc.tobytes()
        #     encoded = base64.b64encode(pdf_raw_bytes).decode("utf-8")

        #     # FINAL: Add to JSON
        #     files_data.append({
        #         "name": f"processed_{idx}.pdf",
        #         "data": encoded
        #     })

        # return {"files": files_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
