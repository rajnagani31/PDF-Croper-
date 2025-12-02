# PDF CROPER API

from operator import le
import os
from fastapi import FastAPI , File, UploadFile,Form,Query,HTTPException 
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from pdf_process import process_pdf
from io import BytesIO
import fitz  # PyMuPDF
import zipfile
import datetime
import base64

import logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/crop-pdf")
async def crop_pdf_editor(
    files: list[UploadFile] = File(...),
    merge: bool = Form(False),
    sort_by_sold: bool = Form(False),
    sort_courier: bool = Form(False),
    remove_white: bool = Form(False),
    print_datetime: bool = Form(False),
    keep_invoice : bool = Form(False),
    keep_invoice_no_crop: bool = Form(False),
    bottom_of_the_table:bool=Form(False),
):
    try:
        filter = {
            "remove_white": remove_white,
            "print_datetime": print_datetime,
            "keep_invoice": keep_invoice,
            "bottom_of_the_table":bottom_of_the_table,
            "keep_invoice_no_crop": keep_invoice_no_crop,
            "sort_by_sold": sort_by_sold,
            "sort_courier": sort_courier,
        }
        logger.info(f"Filter settings: {filter}")
        logger.info("Reading all PDFs into memory...")
        logger.info(f"Bottom of the table filter: {filter['remove_white']}")

        input_pdf = []
        for file in files:
            file_bytes = await file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            input_pdf.append({
                "doc": doc,
                "bytes": file_bytes
            })
        logger.info(f"Total PDFs received: {len(input_pdf)}")

        """ If merge is True then merge all PDF and apply process_pdf() on merged PDF and return single PDF""" 
        if merge:
            logger.info("Merging PDFs...")
            merged_doc = fitz.open()

            for item in input_pdf:
                temp_doc = fitz.open(stream=item["bytes"], filetype="pdf")
                merged_doc.insert_pdf(temp_doc)
        

            merged_bytes = BytesIO(merged_doc.tobytes())
            final_doc = process_pdf(merged_bytes, filter)
            logger.info("Finished processing merged PDF.")

            return StreamingResponse(
                BytesIO(final_doc.tobytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=processed.pdf"}
            )
        
        """ If merge is False & and User pass one PDF then apply process_pdf() on each PDF and return zip of all processed PDFs"""
        if len(input_pdf) == 1:
            logger.info("Single PDF received, processing...")
            single_bytes = BytesIO(input_pdf[0]["bytes"])

            final_doc = process_pdf(single_bytes, filter)
            logger.info("Finished processing single PDF.")

            return StreamingResponse(
                BytesIO(final_doc.tobytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=processed.pdf"}
            )


        """ If merge is False & and User pass multiple PDFs then apply process_pdf() on each PDF and return zip of all processed PDFs"""
        logger.info(f"Multiple PDFs received: processing each...")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            logger.info("Creating ZIP file for processed PDFs with one by one")
            for idx, pdf in enumerate(input_pdf):
                pdf_bytes = BytesIO(pdf["bytes"])
                processed_doc = process_pdf(pdf_bytes, filter)
                processed_bytes = processed_doc.tobytes()
                zip_file.writestr(f"processed_{idx + 1}.pdf", processed_bytes)

        zip_buffer.seek(0)
        logger.info("Finished creating ZIP file for processed PDFs.")
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
        logger.error(f"Error processing PDFs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
