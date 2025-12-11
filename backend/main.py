# PDF CROPER API

from operator import le
import os
from fastapi import FastAPI , File, UploadFile,Form,Query,HTTPException 
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from backend.pdf_process import process_pdf
from io import BytesIO
import fitz  # PyMuPDF
import zipfile
import datetime
import base64
from backend.utils import *
import logging
from backend.pdf_process import merge_and_order_id
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
from fastapi.staticfiles import StaticFiles
import os

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
    # sort_by_sold: bool = Form(False),
    sort_courier: bool = Form(False),
    remove_white: bool = Form(False),
    print_datetime: bool = Form(False),
    # keep_invoice : bool = Form(False),
    keep_invoice_no_crop: bool = Form(False),
    bottom_of_the_table:bool=Form(False),
    separate_order_list: str = Form(""),
):
    try:
        filter = {
            "remove_white": remove_white,
            "print_datetime": print_datetime,
            "bottom_of_the_table":bottom_of_the_table,
            "keep_invoice_no_crop": keep_invoice_no_crop,
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
                "bytes": file_bytes,
                "filename": getattr(file, "filename", f"input_{len(input_pdf)+1}.pdf"),
            })
        logger.info(f"Total PDFs received: {len(input_pdf)}")

        if merge and separate_order_list:
            logger.info("Merging PDFs with separate order IDs and filter...")
            result = merge_and_order_id(input_pdf, separate_order_list, filter)
            return result        

        if merge:
            logger.info("Condition 2: merge only + apply filters")
            merged_doc = fitz.open()

            # Merge PDF pages into single doc
            for item in input_pdf:
                temp_doc = fitz.open(stream=item["bytes"], filetype="pdf")
                merged_doc.insert_pdf(temp_doc)

            # Now run filters on ONE document
            processed_doc = process_pdf(merged_doc.tobytes(), filter)
            return StreamingResponse(
                BytesIO(processed_doc.tobytes()),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={input_pdf[0]['filename']}_merged.pdf"}
            )
                
        # """ If merge is False & and User pass multiple PDFs then apply process_pdf() on each PDF and return zip of all processed PDFs"""
        logger.info("Condition 3: no merge → process each file individually")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for idx, item in enumerate(input_pdf):
                processed_doc = process_pdf(item["bytes"], filter)
                processed_bytes = processed_doc.tobytes()
                zip_file.writestr(f"{input_pdf[idx]['filename']}", processed_bytes)

        zip_buffer.seek(0)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=processed_files.zip"}
        )
    except Exception as e:
        logger.error(f"Error processing PDFs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(CURRENT_DIR, "..", "frontend")

# Serve frontend at "/"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")