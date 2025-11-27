# PDF CROPER API

import os
from fastapi import FastAPI , File, UploadFile,Form,Query,HTTPException 
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from utils import remove_pdf_whitespace, merge_pdfs, get_indian_datetime, print_datetime_on_label,process_pdf
from io import BytesIO
import fitz  # PyMuPDF



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
        file_docs = []
        for file in files:
            file_bytes = await file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            file_docs.append(doc)

        # STEP 2: MERGE IN MEMORY
        if merge:
            merged_doc = fitz.open()
            for d in file_docs:
                merged_doc.insert_pdf(d)
        else:
            merged_doc = file_docs[0]

        # STEP 3: APPLY process_pdf()
        merged_bytes = merged_doc.tobytes()
        final_doc = process_pdf(merged_bytes, settings)

        # STEP 4: RETURN PDF
        return StreamingResponse(
            BytesIO(final_doc.tobytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=processed.pdf"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
