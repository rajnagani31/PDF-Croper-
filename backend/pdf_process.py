from utils import _detect_courier, _extract_quantity ,create_company_summary,create_order_summary ,create_courier_summary
from utils import *
import fitz
from operator import le
import os
from fastapi import FastAPI , File, UploadFile,Form,Query,HTTPException 
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from io import BytesIO
import fitz  # PyMuPDF
import zipfile
import datetime
import base64
from utils import *
import logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


def process_pdf(input_pdf, filter):
    original = fitz.open(stream=input_pdf, filetype="pdf")
    final_doc = fitz.open()

    # STEP 1 — SORT FIRST (ALWAYS USE ORIGINAL TEXT PDF)
    working_doc = original  # default

    if filter.get("sort_courier"):
        pdf = sort_courier(original)
        working_doc = pdf

    if filter.get("print_datetime"):
        try:
            pass
        except:
            pass

    if filter.get("keep_invoice_no_crop"):
        try:
            pass
        except:
            pass

    # STEP 2 — APPLY REMOVE WHITE AFTER SORTING
    if filter.get("remove_white"):
        try:
            working_doc = remove_pdf_whitespace(working_doc)
        except:
            pass

    # STEP 3 — Insert final working pages

    final_doc.insert_pdf(working_doc)

    # STEP 4 — Add Summary Page at End
    if filter.get("bottom_of_the_table"):
        try:
            extracted_data = extract_meesho_data(original)
            if extracted_data:
                order_summary = create_order_summary(extracted_data)
                courier_summary = create_courier_summary(extracted_data)
                company_summary = create_company_summary(extracted_data)

                buffer = create_pdf_report(order_summary, courier_summary, company_summary)
                summary_doc = fitz.open(stream=buffer.getvalue(), filetype="pdf")

                final_doc.insert_pdf(summary_doc)

        except Exception as e:
            logger.exception(e)

    return final_doc




def merge_and_order_id(input_pdf, separate_order_list, filter):
    
    order_ids = []
    if separate_order_list and separate_order_list.strip():
        # split by newline or comma - handle commas as well
        raw_lines = [line.strip() for line in separate_order_list.replace(",", "\n").splitlines()]
        order_ids = [o for o in raw_lines if o]
        logger.info(f"User requested separate extraction for order ids: {order_ids}")
    
    if order_ids:
        selected_doc = fitz.open()   # final combined doc with selected orders
        cleaned_doc = fitz.open()    # final combined doc with non-selected orders

        logger.info("Merging PDFs...")
        merged_doc = fitz.open()


        for item in input_pdf:
            temp_doc = fitz.open(stream=item["bytes"], filetype="pdf")
            merged_doc.insert_pdf(temp_doc)
            
        print('1')
        for file in input_pdf:
            original_doc = fitz.open(stream=file["bytes"], filetype="pdf")

            # Step 1 – Extract pages per order
            orders_pages_map, pages_to_remove = extract_orders_from_pdf(original_doc, order_ids)

            # Step 2 – Add selected pages into selected_doc
            selected_pages = []
            for pages in orders_pages_map.values():
                selected_pages.extend(pages)
            selected_pages = sorted(set(selected_pages))  # dedupe

            if selected_pages:
                for p in selected_pages:
                    selected_doc.insert_pdf(original_doc, from_page=p, to_page=p)

            # Step 3 – Add remaining pages into cleaned_doc
            for p in range(len(original_doc)):
                if p not in selected_pages:
                    cleaned_doc.insert_pdf(original_doc, from_page=p, to_page=p)

    
        # Step 4 – Apply filters
        final_selected = process_pdf(selected_doc.tobytes(), filter)   # pass bytes directly
        final_cleaned = process_pdf(cleaned_doc.tobytes(), filter)
        print('data',input_pdf[0]['filename'])
        # Step 5 – Return ZIP with exactly 2 PDFs
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr(f"{input_pdf[0]['filename']}_all_merged.pdf", final_selected.tobytes())
            zip_file.writestr("cleaned_original.pdf", final_cleaned.tobytes())

        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=orders_output.zip"}
        )


def only_separate_order_with_filter(input_pdf, separate_order_list, filter):
    order_ids = []
    if separate_order_list and separate_order_list.strip():
        # split by newline or comma - handle commas as well
        raw_lines = [line.strip() for line in separate_order_list.replace(",", "\n").splitlines()]
        order_ids = [o for o in raw_lines if o]
        logger.info(f"User requested separate extraction for order ids: {order_ids}")
    
    if order_ids:
        selected_doc = fitz.open()   # final combined doc with selected orders
        cleaned_doc = fitz.open()    # final combined doc with non-selected orders            

        for file in input_pdf:
            original_doc = fitz.open(stream=file["bytes"], filetype="pdf")

            # Step 1 – Extract pages per order
            orders_pages_map, pages_to_remove = extract_orders_from_pdf(original_doc, order_ids)

            # Step 2 – Add selected pages into selected_doc
            selected_pages = []
            for pages in orders_pages_map.values():
                selected_pages.extend(pages)
            selected_pages = sorted(set(selected_pages))  # dedupe

            if selected_pages:
                for p in selected_pages:
                    selected_doc.insert_pdf(original_doc, from_page=p, to_page=p)

            # Step 3 – Add remaining pages into cleaned_doc
            for p in range(len(original_doc)):
                if p not in selected_pages:
                    cleaned_doc.insert_pdf(original_doc, from_page=p, to_page=p)

        # Step 4 – Apply filters
        final_selected = process_pdf(selected_doc.tobytes(), filter)   # pass bytes directly
        final_cleaned = process_pdf(cleaned_doc.tobytes(), filter)

        # Step 5 – Return ZIP with exactly 2 PDFs
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("selected_orders.pdf", final_selected.tobytes())
            zip_file.writestr("cleaned_original.pdf", final_cleaned.tobytes())

        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=orders_output.zip"}
        )
