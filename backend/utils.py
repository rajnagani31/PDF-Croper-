import fitz  # PyMuPDF
from PIL import Image
import io
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import pytz
import re


def get_indian_datetime():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    return now.strftime("%d-%m-%Y %I:%M %p") 

def extract_seller(text: str):
    """
    Extract seller/vendor name from page text.
    """
    if not text:
        return None

    # Patterns for: Sold by: NAME  / Seller: NAME
    patterns = [
        r"(?:sold\s*by|seller)\s*[:\-]?\s*(.+)",
    ]

    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            seller = m.group(1).strip()
            seller = seller.splitlines()[0].strip()
            seller = seller.rstrip(".,;:")
            return seller

    return None



def remove_pdf_whitespace(input_pdf_path: str, output_pdf_path: str = "full.pdf", dpi: int = 150):
    """
    Removes white space around content for each page of the PDF.
    Saves a trimmed PDF.

    Args:
        input_pdf_path: path to input PDF
        output_pdf_path: path to save trimmed PDF
        dpi: rendering DPI (higher = better quality)
    """

    input_pdf = Path(input_pdf_path)
    output_pdf = Path(output_pdf_path)

    if not input_pdf.exists():
        raise FileNotFoundError(f"File not found: {input_pdf}")

    scale = dpi / 72.0  # PDF points -> pixels

    src = fitz.open(str(input_pdf))
    out = fitz.open()  # new PDF

    for pno in range(len(src)):
        page = src[pno]

        # Detect content bounding box using words first
        words = page.get_text("words")
        if words:
            x0 = min(w[0] for w in words)
            y0 = min(w[1] for w in words)
            x1 = max(w[2] for w in words)
            y1 = max(w[3] for w in words)
            bbox = fitz.Rect(x0, y0, x1, y1)
        else:
            # fallback: detect using text blocks
            blocks = page.get_text("dict").get("blocks", [])
            rects = [fitz.Rect(b["bbox"]) for b in blocks]
            bbox = sum(rects, rects[0]) if rects else page.rect
        
        # Add small margin to avoid cutting edges
        margin = 4
        page_rect = page.rect
        clip = fitz.Rect(
            max(page_rect.x0, bbox.x0 - margin),
            max(page_rect.y0, bbox.y0 - margin),
            min(page_rect.x1, bbox.x1 + margin),
            min(page_rect.y1, bbox.y1 + margin),
        )

        # Render only the clipped area
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert image to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        # New PDF page with same clip size
        new_page = out.new_page(width=clip.width, height=clip.height)
        new_page.insert_image(
            fitz.Rect(0, 0, clip.width, clip.height),
            stream=img_bytes.read()
        )

    out.save(str(output_pdf))
    out.close()
    src.close()

    return str(output_pdf)

# remove_pdf_whitespace("c-21.pdf")


def merge_pdfs(input_pdf_list: List[str], output_pdf_path: str = "merged___.pdf") -> str:
    """
    Merge multiple PDFs into one final PDF.

    Args:
        input_pdf_list: list of PDF file paths
        output_pdf_path: path to save the merged PDF

    Returns:
        output_pdf_path
    """

    if not input_pdf_list:
        raise ValueError("No PDFs provided to merge.")

    # Ensure all input files exist
    pdf_paths = [Path(p) for p in input_pdf_list]
    for p in pdf_paths:
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

    # Create output PDF
    out = fitz.open()

    # Insert pages from each input PDF
    for pdf_file in pdf_paths:
        src = fitz.open(str(pdf_file))
        out.insert_pdf(src)
        src.close()

    # Save output file
    out.save(output_pdf_path)
    out.close()

    return output_pdf_path


# merge_pdfs([
    # "g-21.pdf",
    # "c-21.pdf",
    # "c-21.pdf"
# ])


def print_datetime_on_label(input_pdf: str, output_pdf: str = "final_with_datetime.pdf",
                            position: str = "bottom-right"):

    doc = fitz.open(input_pdf)
    now = get_indian_datetime()

    for page in doc:
        w, h = page.rect.width, page.rect.height

        if position == "top-left":
            x, y = 20, 20
        elif position == "top-right":
            x, y = w - 150, 20
        elif position == "bottom-left":
            x, y = 20, h - 40
        else:  # bottom-right
            x, y = w - 150, h - 40

        page.insert_text((x, y), now, fontsize=10, color=(0, 0, 0))

    doc.save(output_pdf)
    doc.close()
    return output_pdf

# print_datetime_on_label("c-21.pdf")





def sort_vendor_wise(input_pdf: str, output_pdf: str = "vendor_sorted.pdf") -> str:
    """
    Sort pages in a PDF vendor-wise using 'Sold by' line.
    Sorting is alphabetical (A → Z).
    """

    input_path = Path(input_pdf)
    if not input_path.exists():
        raise FileNotFoundError(f"PDF not found: {input_pdf}")

    doc = fitz.open(str(input_pdf))
    pages_by_vendor = {}

    # -----------------------------
    # Extract vendor from each page
    # -----------------------------
    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text")

        vendor = extract_seller(text)
        if not vendor:
            vendor = "UNKNOWN"

        pages_by_vendor.setdefault(vendor, []).append(pno)

    # ----------------------------------------
    # Sort vendors A → Z (Vendor-wise sorting)
    # ----------------------------------------
    sorted_vendors = sorted(pages_by_vendor.keys(), key=lambda x: x.lower())

    # -----------------------------
    # Create sorted merged PDF
    # -----------------------------
    out = fitz.open()

    for vendor in sorted_vendors:
        for pno in pages_by_vendor[vendor]:
            out.insert_pdf(doc, from_page=pno, to_page=pno)

    out.save(output_pdf)
    out.close()
    doc.close()

    return output_pdf

# sort_vendor_wise("merged.pdf")




def sort_courier_wise(input_pdf: str, output_pdf: str = "courier_sorted.pdf") -> str:
    """
    Sort pages of a PDF by courier name (Delhivery / Bluedart / Xpressbees / Ekart / etc.)
    Returns one final merged PDF sorted courier-wise (A → Z).
    """

    courier_keywords = [
        "delhivery", "bluedart", "xpress", "Xpress bees", "ekart", "dtdc",
        "fedex", "ups", "royal", "valmo", "gol", "blu", "Shadowfax"
    ]

    def detect_courier(text: str) -> str:
        """Detect courier from text using keyword matching."""
        if not text:
            return "UNKNOWN"

        t = text.lower()

        for kw in courier_keywords:
            if kw in t:
                if "xpress" in kw:
                    return "Xpress Bees"
                if "bluedart" in kw or kw == "blu":
                    return "Bluedart"
                if "delhivery" in kw:
                    return "Delhivery"
                if "shadowfax" in kw:
                    return "Shadowfax"
                if "valmo" in kw or "gol" in kw:
                    return "Valmo/Gol"
                if "ekart" in kw:
                    return "Ekart"
                if "dtdc" in kw:
                    return "DTDC"
                if "fedex" in kw:
                    return "FedEx"
                if "ups" in kw:
                    return "UPS"
                if "royal" in kw:
                    return "Royal"
                return kw.upper()

        return "UNKNOWN"

    input_path = Path(input_pdf)
    if not input_path.exists():
        raise FileNotFoundError(f"PDF not found: {input_pdf}")

    doc = fitz.open(str(input_pdf))
    pages_by_courier = {}

    # ------------------------
    # Detect courier per page
    # ------------------------
    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text") or ""
        courier = detect_courier(text)

        if courier not in pages_by_courier:
            pages_by_courier[courier] = []

        pages_by_courier[courier].append(pno)

    # ------------------------
    # Sort courier alphabetically (A → Z)
    # ------------------------
    sorted_couriers = sorted(pages_by_courier.keys(), key=lambda x: x.lower())

    # ------------------------
    # Build final sorted PDF
    # ------------------------
    out = fitz.open()

    for courier in sorted_couriers:
        for pno in pages_by_courier[courier]:
            out.insert_pdf(doc, from_page=pno, to_page=pno)

    out.save(output_pdf)
    out.close()
    doc.close()

    return output_pdf

# sort_courier_wise("merged.pdf")


def keep_invoice(input_pdf: str, output_pdf: str = "invoice_original.pdf"):
    import shutil
    shutil.copy(input_pdf, output_pdf)
    return output_pdf

# keep_invoice("c-21.pdf")

def keep_invoice_no_crop(input_pdf: str, output_pdf: str = "invoice_no_crop.pdf"):
    import shutil
    shutil.copy(input_pdf, output_pdf)
    return output_pdf

# keep_invoice_no_crop("c-21.pdf")



def treat_valmo(input_pdf: str, output_pdf: str = "treat_valmo.pdf") -> str:
    """
    Sort pages in a PDF courier-wise (A → Z).
    Valmo, Valmo Express, GOL/Valmo all treated as 'Valmo'.
    Returns one final merged PDF.
    """

    def detect_courier(text: str) -> str:
        if not text:
            return "UNKNOWN"

        t = text.lower()

        # --- Treat valmoexpress same as valmo ---
        if "valmo" in t or "gol" in t:
            return "Valmo"

        # --- Other couriers ---
        if "delhivery" in t:
            return "Delhivery"
        if "xpress" in t:
            return "XpressBees"
        if "bluedart" in t or "blu" in t:
            return "Bluedart"
        if "ekart" in t:
            return "Ekart"
        if "dtdc" in t:
            return "DTDC"
        if "fedex" in t:
            return "FedEx"
        if "ups" in t:
            return "UPS"
        if "royal" in t:
            return "Royal"

        return "UNKNOWN"

    # -------------------------
    # Load PDF
    # -------------------------
    input_path = Path(input_pdf)
    if not input_path.exists():
        raise FileNotFoundError(f"PDF not found: {input_pdf}")

    doc = fitz.open(input_pdf)
    pages_by_courier = {}

    # -------------------------
    # Detect courier per page
    # -------------------------
    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text") or ""
        courier = detect_courier(text)

        if courier not in pages_by_courier:
            pages_by_courier[courier] = []

        pages_by_courier[courier].append(pno)

    # -------------------------
    # Sort courier A → Z
    # -------------------------
    sorted_couriers = sorted(pages_by_courier.keys(), key=lambda x: x.lower())

    # -------------------------
    # Create final sorted PDF
    # -------------------------
    out = fitz.open()

    for courier in sorted_couriers:
        for pno in pages_by_courier[courier]:
            out.insert_pdf(doc, from_page=pno, to_page=pno)

    out.save(output_pdf)
    out.close()
    doc.close()

    return output_pdf

# treat_valmo("merged.pdf")


def multi_order_at_bottom(input_pdf: str, output_pdf: str = "multi_order_output.pdf") -> str:
    """
    Simple version: detects ALL order_ids on each page.
    The FIRST order_id is treated as the main order.
    Any EXTRA order_ids are listed at the bottom of the page.

    input_pdf  -> PDF with invoice pages
    output_pdf -> PDF with multi-order section added
    """

    # A simple order-id pattern for your invoices (numbers, optionally _1, _2 etc)
    ORDER_REGEX = r"\b(\d{8,}(?:_\d+)?)\b"

    input_path = Path(input_pdf)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_pdf}")

    src = fitz.open(str(input_path))
    out = fitz.open()

    for pno in range(len(src)):
        page = src[pno]
        text = page.get_text("text") or ""

        # find all order IDs on this page
        order_ids = re.findall(ORDER_REGEX, text)

        # if only one order OR none → copy as is
        if len(order_ids) <= 1:
            out.insert_pdf(src, from_page=pno, to_page=pno)
            continue

        main_order = order_ids[0]
        extra_orders = order_ids[1:]

        # Copy original page to output
        out.insert_pdf(src, from_page=pno, to_page=pno)
        new_page = out[-1]

        # bottom box dimensions
        rect = new_page.rect
        box_height = 50 + 12 * len(extra_orders)
        box = fitz.Rect(20, rect.height - box_height - 20, rect.width - 20, rect.height - 20)

        # white background
        new_page.draw_rect(box, fill=(1, 1, 1), color=(1, 1, 1))

        # header
        y = box.y0 + 10
        new_page.insert_text((box.x0 + 10, y), "Other Orders:", fontsize=10)
        y += 15

        # list extra order IDs
        for oid in extra_orders:
            new_page.insert_text((box.x0 + 10, y), f"- {oid}", fontsize=9)
            y += 12

    out.save(output_pdf)
    out.close()
    src.close()

    return output_pdf

# multi_order_at_bottom("merged.pdf")



ORDER_REGEX = r"\b(\d{8,}(?:_\d+)?)\b"  # matches long numeric ids, optionally with _1, _2


def _extract_first_order_id(text: str) -> str:
    """Return the first matching order id in the text or empty string if none."""
    if not text:
        return ""
    m = re.search(ORDER_REGEX, text)
    return m.group(1) if m else ""


def add_picklist_after(
    input_pdf: str,
    output_pdf: str = "with_picklists.pdf",
    after_n: int = 10,
    enabled: bool = True,
    picklist_title: str = "Picklist",
) -> str:
    """
    Insert a simple picklist page after every `after_n` orders detected in the PDF.
    - input_pdf: path to source PDF
    - output_pdf: path to write final PDF
    - after_n: number of order pages after which to insert picklist (default 10)
    - enabled: if False -> copy input to output and return (no picklists)
    - picklist_title: title string printed on each picklist page

    Returns path to output_pdf.
    """
    in_path = Path(input_pdf)
    if not in_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    # If picklist feature disabled -> simple copy (no processing)
    if not enabled:
        # fast copy by reading and writing with fitz
        doc_in = fitz.open(str(in_path))
        doc_in.save(output_pdf)
        doc_in.close()
        return str(Path(output_pdf).resolve())

    src = fitz.open(str(in_path))
    out = fitz.open()

    # accumulator for order ids in current chunk
    chunk_order_ids: List[str] = []
    total_orders_seen = 0

    def flush_picklist(chunk_ids: List[str], insert_after_doc: fitz.Document):
        """
        Helper to append a picklist page to `out` describing chunk_ids.
        We build a simple text layout: title + list of order ids + counts.
        """
        if not chunk_ids:
            return
        # create a new page same size as the source pages (use first page size or A4 fallback)
        # prefer to use standard size of first page if available
        if len(src) > 0:
            ref_rect = src[0].rect
            w, h = ref_rect.width, ref_rect.height
        else:
            w, h = 595, 842  # approx A4 pts fallback

        pick_page = out.new_page(width=w, height=h)

        # Compose text
        header = f"{picklist_title} — {len(chunk_ids)} orders"
        lines = [header, "-" * 80, ""]
        for idx, oid in enumerate(chunk_ids, start=1):
            # keep lines reasonably short; if id is too long, you may truncate
            lines.append(f"{idx}. {oid}")
        lines.append("")
        lines.append(f"Total orders in this picklist: {len(chunk_ids)}")

        # Insert textbox centered-ish with margins
        margin_left = 40
        margin_top = 40
        text_box = fitz.Rect(margin_left, margin_top, w - margin_left, h - margin_top)
        text_content = "\n".join(lines)
        # default font size and spacing
        pick_page.insert_textbox(text_box, text_content, fontsize=11, fontname="helv", align=0)

    # Iterate pages in source doc
    for pno in range(len(src)):
        page = src[pno]
        # extract first/primary order id on this page
        text = page.get_text("text") or ""
        order_id = _extract_first_order_id(text)

        # Always copy current page to output
        out.insert_pdf(src, from_page=pno, to_page=pno)

        if order_id:
            chunk_order_ids.append(order_id)
            total_orders_seen += 1

        # If we've collected after_n orders, flush picklist immediately after this inserted page
        if len(chunk_order_ids) >= after_n:
            flush_picklist(chunk_order_ids, out)
            chunk_order_ids = []  # reset chunk

    # After loop: if leftover orders exist, append final picklist (optional behavior)
    if chunk_order_ids:
        flush_picklist(chunk_order_ids, out)

    # Save and cleanup
    out.save(str(output_pdf))
    out.close()
    src.close()

    return str(Path(output_pdf).resolve())

# add_picklist_after("merged.pdf")

def separate_review_orders(input_pdf: str, output_folder: str = "review_output") -> Dict[str, str]:
    """
    Splits pages into two PDFs:
      - normal_orders.pdf   (pages NOT matching review keywords)
      - review_orders.pdf   (pages matching review keywords)

    Returns a dict containing paths for files that were actually created.
    If no pages fall into a bucket, that bucket will not be saved or returned.
    """

    REVIEW_KEYWORDS = ["review required", "on hold", "hold", "qc"]

    input_path = Path(input_pdf)
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    src = fitz.open(str(input_path))
    normal_doc = fitz.open()      # For non-review orders
    review_doc = fitz.open()      # For review-required orders

    try:
        for pno in range(len(src)):
            page = src[pno]
            text = (page.get_text("text") or "").lower()

            # Detect review keywords (simple substring match)
            is_review = any(kw in text for kw in REVIEW_KEYWORDS)

            if is_review:
                review_doc.insert_pdf(src, from_page=pno, to_page=pno)
            else:
                normal_doc.insert_pdf(src, from_page=pno, to_page=pno)

        results = {}

        # Save only if there are pages
        normal_path = out_dir / "normal_orders.pdf"
        review_path = out_dir / "review_orders.pdf"

        if normal_doc.page_count > 0:
            normal_doc.save(str(normal_path))
            results["normal_orders"] = str(normal_path)

        if review_doc.page_count > 0:
            review_doc.save(str(review_path))
            results["review_orders"] = str(review_path)

        # If neither produced anything, raise an informative error
        if not results:
            raise ValueError("No pages found to split — source PDF produced zero pages for both buckets.")

        return results

    finally:
        # Always close docs to release file handles
        try:
            normal_doc.close()
        except Exception:
            pass
        try:
            review_doc.close()
        except Exception:
            pass
        src.close()

# separate_review_orders("merged.pdf")