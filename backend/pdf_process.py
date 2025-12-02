from utils import _detect_courier, _extract_quantity
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

    # Step 1 — remove whitespace or use original
    if filter['remove_white']:
        pdf = remove_pdf_whitespace(original)
        working_doc = pdf
    else:
        working_doc = original

    # Step 2 — APPLY sort_courier (ONLY NEW ADDITION)
    if filter.get("sort_courier"):
        try:
            # collect metadata (page_no, courier, qty)
            page_meta = []
            for pno in range(len(working_doc)):
                text = working_doc[pno].get_text("text") or ""
                courier = _detect_courier(text) or "__unknown__"
                qty = _extract_quantity(text)
                page_meta.append((pno, courier, qty))

            # count pages per courier
            courier_counts = {}
            for _, courier, _ in page_meta:
                courier_counts[courier] = courier_counts.get(courier, 0) + 1

            # first appearance map
            first_appearance = {}
            for pno, courier, _ in page_meta:
                if courier not in first_appearance:
                    first_appearance[courier] = pno

            # sort couriers by (-count, first_appearance)
            couriers_sorted = sorted(
                courier_counts.keys(),
                key=lambda c: (-courier_counts.get(c, 0), first_appearance.get(c, 10**9))
            )

            # ensure unknown goes last
            if "__unknown__" in couriers_sorted:
                couriers_sorted = [c for c in couriers_sorted if c != "__unknown__"] + ["__unknown__"]

            # build final order: for each courier group, sort pages by qty (None last, ascending),
            # and when qty equal preserve original page order by using pno as secondary key
            final_order = []
            for courier in couriers_sorted:
                pages = [(pno, qty) for (pno, c, qty) in page_meta if c == courier]
                pages.sort(key=lambda t: (
                    1 if t[1] is None else 0,                 # None last
                    t[1] if isinstance(t[1], int) else 0,     # qty ascending (None handled above)
                    t[0]                                      # stable: original page order tiebreaker
                ))
                final_order.extend([p for p, _ in pages])

            # create sorted_doc and replace working_doc
            sorted_doc = fitz.open()
            for pno in final_order:
                sorted_doc.insert_pdf(working_doc, from_page=pno, to_page=pno)

            working_doc = sorted_doc

        except Exception:
            # on any error, keep working_doc unchanged
            pass
    # Step 3 — insert sorted/unsorted pages into final_doc
    final_doc.insert_pdf(working_doc)

    # Step 4 — print datetime (unchanged)
    if filter['print_datetime']:
        pass

    # Step 5 — bottom_of_the_table (unchanged)
    if filter['bottom_of_the_table']:
        extracted_data = extract_meesho_data(original)

    
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

        # result = merge_and_order_id(input_pdf)
        # return result

        for item in input_pdf:
            temp_doc = fitz.open(stream=item["bytes"], filetype="pdf")
            merged_doc.insert_pdf(temp_doc)
            

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
        final_selected = process_pdf(BytesIO(selected_doc.tobytes()), filter)
        final_cleaned = process_pdf(BytesIO(cleaned_doc.tobytes()), filter)

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
        final_selected = process_pdf(BytesIO(selected_doc.tobytes()), filter)
        final_cleaned = process_pdf(BytesIO(cleaned_doc.tobytes()), filter)

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
