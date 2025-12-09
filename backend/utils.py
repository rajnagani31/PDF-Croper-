import fitz  # PyMuPDF
from PIL import Image
import io
from pathlib import Path
from datetime import datetime
import pytz
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO
from typing import List, Dict, Optional, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import io
import fitz
from PIL import Image


def remove_pdf_whitespace(doc: fitz.Document, dpi: int = 90, jpeg_quality: int = 60):
    """
    Crop page → Render cropped region → convert to JPEG → embed → extremely small PDF output.
    """
    scale = dpi / 72
    out = fitz.open()

    for pno in range(len(doc)):
        page = doc[pno]

        # find bounding box
        words = page.get_text("words")
        if words:
            x0 = min(w[0] for w in words)
            y0 = min(w[1] for w in words)
            x1 = max(w[2] for w in words)
            y1 = max(w[3] for w in words)
            bbox = fitz.Rect(x0, y0, x1, y1)
        else:
            blocks = page.get_text("dict").get("blocks", [])
            rects = [fitz.Rect(b["bbox"]) for b in blocks if "bbox" in b]
            bbox = (sum(rects, rects[0]) if rects else page.rect)

        # add margin + clamp to page
        margin = 4
        clip = fitz.Rect(
            bbox.x0 - margin,
            bbox.y0 - margin,
            bbox.x1 + margin,
            bbox.y1 + margin
        )
        clip &= page.rect

        if clip.width <= 0 or clip.height <= 0:
            clip = page.rect

        # Render cropped area
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)

        # Convert pixmap → PIL image
        mode = "RGB" if pix.n < 4 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        # Convert to grayscale (optional but reduces size heavily)
        img = img.convert("L")

        # Save JPEG with compression
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG", quality=jpeg_quality, optimize=True)
        img_bytes.seek(0)

        # Create new PDF page
        new_page = out.new_page(width=clip.width, height=clip.height)
        new_page.insert_image(
            fitz.Rect(0, 0, clip.width, clip.height),
            stream=img_bytes.getvalue()
        )

    return out

def sort_courier(original):
        try:
            page_meta = []
            for pno in range(len(original)):
                text = original[pno].get_text("text") or ""
                courier = _detect_courier(text) or "__unknown__"
                qty = _extract_quantity(text)
                page_meta.append((pno, courier, qty))

            # Count pages per courier
            courier_counts = {}
            first_appearance = {}

            for pno, courier, _ in page_meta:
                courier_counts[courier] = courier_counts.get(courier, 0) + 1
                if courier not in first_appearance:
                    first_appearance[courier] = pno

            # Sorting rule
            couriers_sorted = sorted(
                courier_counts.keys(),
                key=lambda c: (-courier_counts[c], first_appearance[c])
            )

            # Move unknown last
            if "__unknown__" in couriers_sorted:
                couriers_sorted.remove("__unknown__")
                couriers_sorted.append("__unknown__")

            # Build final sorted order
            final_order = []
            for courier in couriers_sorted:
                pages = [(pno, qty) for (pno, c, qty) in page_meta if c == courier]
                pages.sort(key=lambda t: (
                    1 if t[1] is None else 0,
                    t[1] if isinstance(t[1], int) else 0,
                    t[0]
                ))
                final_order.extend([p for p, _ in pages])

            # Create sorted PDF
            sorted_doc = fitz.open()
            for pno in final_order:
                sorted_doc.insert_pdf(original, from_page=pno, to_page=pno)

            working_doc = sorted_doc
            return working_doc

        except Exception as e:
            print("sort error:", e)
            working_doc = original



def extract_meesho_data(pdf_input) -> List[Dict]:
    """
    Extract structured data from Meesho shipping label PDF
    
    Args:
        pdf_input: Can be BytesIO or fitz.Document
    
    Returns:
        List of dictionaries containing extracted fields
    """
    # Handle both BytesIO and fitz.Document
    if isinstance(pdf_input, fitz.Document):
        doc = pdf_input
        should_close = False
    else:
        doc = fitz.open(stream=pdf_input, filetype="pdf")
        should_close = True
    
    extracted_data = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        record = {}
        lines = [l for l in text.splitlines() if l.strip()]
        product_details = {}
        for i , line in enumerate(lines):
            if line.lower() == "product details":
                try:
                    sku     = lines[i+6]
                    size    = lines[i+7]
                    qty     = lines[i+8]
                    color   = lines[i+9]
                    orderno = lines[i+10]
                    product_details.update({'SKU':sku ,'Size':size,'QTY':qty,'Color':color,'Order No':orderno})
                except:
                    return None
        
        record['SKU'] = product_details.get('SKU','Unknown').strip()
        record['Size'] = product_details.get('Size','Free Size').strip()
        record['QTY'] = int(product_details.get('QTY',1))
        record['Color'] = product_details.get('Color','Unknown').strip()
        record['Order No'] = product_details.get('Order No','Unknown').strip() 


        # Extract Courier Partner from shipping section
        couriers = ['Delhivery', 'Shadowfax', 'Valmo', 'Xpress Bees', 'Bluedart', 'Ecom', 'DTDC', 'Ekart']
        record['Courier'] = 'Unknown'
        text_upper = text.upper()
        for courier in couriers:
            if courier.upper() in text_upper:
                record['Courier'] = courier
                break
        
        seller_pattern = r"Sold\s+by\s*:\s*(.+)"
        seller_name = re.search(seller_pattern, text, re.IGNORECASE)
        
        record['Seller'] = seller_name.group(1).strip() if seller_name else 'Unknown'
        extracted_data.append(record)
    
    if should_close:
        doc.close()
    
    return extracted_data


def create_order_summary(data: List[Dict]) -> pd.DataFrame:
    """
    Create ORDER SUMMARY TABLE
    Group by SKU + Size + Color and count QTY by orders
    """
    df = pd.DataFrame(data)
    #Group by row Finde same Group like
    #Group 1 → (A, M, Red, QTY=2)
    #Group 2 → (A, M, Red, QTY=1)
    breakdown = df.groupby(['SKU','Size','Color','QTY']).size().reset_index(name='ORD') # Count orders quantity using same SKU/Size/Color/QTY
    breakdown = breakdown[['ORD','QTY','Size','Color','SKU']].sort_values(['SKU','Size','Color','QTY'])
    return breakdown


def create_courier_summary(data: List[Dict]) -> pd.DataFrame:
    """
    Create COURIER-WISE TOTAL PACKAGE TABLE
    Count packages by courier partner
    """
    df = pd.DataFrame(data)
    
    courier_summary = df.groupby('Courier').size().reset_index()
    courier_summary.columns = ['Courier Partner', 'Package']
    
    # Sort by package count descending
    courier_summary = courier_summary.sort_values('Package', ascending=False)
    
    return courier_summary


def create_company_summary(data: List[Dict]) -> pd.DataFrame:
    """
    Create COMPANY-WISE TOTAL PACKAGE TABLE
    Count packages by seller/company
    """
    df = pd.DataFrame(data)
    company_summary = df.groupby('Seller').size().reset_index()
    company_summary.columns = ['Sold By', 'Package']
    
    # Sort by package count descending
    company_summary = company_summary.sort_values('Package', ascending=False)
    
    return company_summary


def create_pdf_report(order_summary: pd.DataFrame, 
                      courier_summary: pd.DataFrame, 
                      company_summary: pd.DataFrame,
                      output_path: str = None) -> BytesIO:
    """
    Create PDF with all three tables using simple black borders
    """
    # Create PDF buffer
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer if output_path is None else output_path,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    
    # Container for elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    heading_style = styles['Heading2']
    
    # Title
    title = Paragraph("Shipping Label Summary Repor", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.3*inch))
    
    # TABLE 1: ORDER SUMMARY
    elements.append(Paragraph("1. ORDER SUMMARY TABLE", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Add total row to order summary
    total_orders = order_summary['ORD'].sum()
    total_qty = order_summary['QTY'].sum()
    total_row = pd.DataFrame({
        'ORD': [f'TOTAL: {total_orders}'],
        'QTY': [total_qty],
        'Size': [''],
        'Color': [''],
        'SKU': ['']
    })
    order_summary_with_total = pd.concat([order_summary, total_row], ignore_index=True)
    
    # Convert to list for table
    order_data = [order_summary_with_total.columns.tolist()] + order_summary_with_total.values.tolist()
    
    order_table = Table(order_data, colWidths=[60, 60, 80, 80, 200])
    order_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    elements.append(order_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # TABLE 2: COURIER-WISE
    elements.append(Paragraph("2. COURIER-WISE TOTAL PACKAGE", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    courier_data = [courier_summary.columns.tolist()] + courier_summary.values.tolist()
    
    courier_table = Table(courier_data, colWidths=[300, 100])
    courier_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    
    elements.append(courier_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # TABLE 3: COMPANY-WISE
    elements.append(Paragraph("3. COMPANY-WISE TOTAL PACKAGE", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    company_data = [company_summary.columns.tolist()] + company_summary.values.tolist()
    
    company_table = Table(company_data, colWidths=[300, 100])
    company_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    
    elements.append(company_table)
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF bytes
    if output_path is None:
        buffer.seek(0)
        return buffer
    else:
        return None



COURIER_KEYWORDS = [
    "Xpress bees",
    "Delhivery",
    "Shadowfax",
    "valmo/gol",
    "Valmo",
    "bluedart",
]

# compile regexes (longest first)
_COURIER_REGEXES = [
    (kw, re.compile(r"\b" + re.escape(kw.lower()) + r"\b", flags=re.IGNORECASE))
    for kw in sorted(COURIER_KEYWORDS, key=lambda s: -len(s))
]

# Qty detection regex
_QTY_PATTERNS = [
    # old pattern (still useful for some PDFs)
    re.compile(
        r"\bQty\b(?:\s*|\s*[:\-]\s*|\s*\n\s*)([0-9]{1,6})\b",
        flags=re.IGNORECASE
    ),

    # NEW pattern for table-style PDFs:
    # Looks for a row where the 3rd column is a number
    re.compile(
        r"(?mi)^.+?\s+.+?\s+([0-9]{1,6})\s+.+?$"
    ),
]



# -----------------------------------------------------
#  COURIER DETECTION
# -----------------------------------------------------
def _detect_courier(text: str) -> str:
    txt = (text or "").lower()
    for kw, rx in _COURIER_REGEXES:
        if rx.search(txt):
            return kw.lower()
    return "__unknown__"


# -----------------------------------------------------
#  FIXED QUANTITY EXTRACTION
# -----------------------------------------------------
def _extract_quantity(text: str) -> Optional[int]:
    if not text:
        return None

    lines = text.splitlines()
    cleaned = []
    capture = False

    # --- 1) Capture only the Product Details block ---
    for line in lines:
        l = line.strip()

        # Start collecting after encountering "Product Details"
        if "product details" in l.lower():
            capture = True
            continue

        # Stop collecting once invoice section begins
        if capture and (
            "tax invoice" in l.lower()
            or "sold by" in l.lower()
            or "gstin" in l.lower()
            or "invoice no" in l.lower()
        ):
            break

        if capture:
            cleaned.append(line)

    block = "\n".join(cleaned)

    # --- 2) First, try your original Qty pattern (Qty: 1, Qty 1 etc.) ---
    qty_keyword_patterns = [
        re.compile(
            r"\bQty\b(?:\s*|\s*[:\-]\s*|\s*\n\s*)([0-9]{1,6})\b",
            flags=re.IGNORECASE,
        )
    ]

    for rx in qty_keyword_patterns:
        m = rx.search(block)
        if m:
            return int(m.group(1))

    # --- 3) Table-based Qty extraction ---
    # Detect header line containing SKU | Size | Qty | Color
    header_index = None
    for i, line in enumerate(cleaned):
        h = line.lower()
        if "sku" in h and "size" in h and "qty" in h and "color" in h:
            header_index = i
            break

    if header_index is not None:
        # The next non-empty line is the product row
        for j in range(header_index + 1, len(cleaned)):
            row = cleaned[j].strip()
            if not row:
                continue  # skip blank rows

            parts = row.split()
            # We expect at least 4 columns: SKU | Size | Qty | Color
            if len(parts) >= 3:
                qty_val = parts[2]
                if qty_val.isdigit():
                    return int(qty_val)
            break  # stop after first product row

    # --- 4) Fallback: generic pattern, matches lines like:
    # "something  something  3  something"
    fallback_rx = re.compile(r"(?mi)^.+?\s+.+?\s+([0-9]{1,6})\s+.+?$")
    m = fallback_rx.search(block)
    if m:
        try:
            return int(m.group(1))
        except:
            pass

    # Nothing found
    return None


# -----------------------------------------------------
#  FIXED SORT FUNCTION
# -----------------------------------------------------
def sort_doc_by_courier_and_quantity_fixed(doc: fitz.Document, debug: bool = False) -> fitz.Document:
    # 1. Gather metadata
    page_meta: List[Tuple[int, str, Optional[int], str]] = []
    for pno in range(len(doc)):
        text = doc[pno].get_text("text") or ""
        courier = _detect_courier(text)
        qty = _extract_quantity(text)
        snippet = (text.strip().splitlines()[0] if text.strip() else "")[:140]

        page_meta.append((pno, courier, qty, snippet))

        if debug:
            print(f"[page {pno}] courier={courier}, qty={qty}, snippet={snippet!r}")

    # 2. Count pages per courier
    courier_counts: Dict[str, int] = {}
    for _, courier, _, _ in page_meta:
        courier_counts[courier] = courier_counts.get(courier, 0) + 1

    # 3. First appearance (tie-breaker)
    first_appearance: Dict[str, int] = {}
    for pno, courier, _, _ in page_meta:
        if courier not in first_appearance:
            first_appearance[courier] = pno

    # 4. Sort courier groups
    couriers_sorted = sorted(
        courier_counts.keys(),
        key=lambda c: (-courier_counts[c], first_appearance.get(c, 10**9))
    )

    # Move unknown to last
    if "__unknown__" in couriers_sorted:
        couriers_sorted = [c for c in couriers_sorted if c != "__unknown__"] + ["__unknown__"]

    if debug:
        print("\nCourier Order:")
        for c in couriers_sorted:
            print(f"  {c}: count={courier_counts[c]}, first_at={first_appearance[c]}")

    # 5. Sort pages inside each courier group by Qty
    final_order = []
    for courier in couriers_sorted:
        pages = [(pno, qty) for (pno, c, qty, _) in page_meta if c == courier]

        # FIXED SORT: None goes last, quantities ascend
        pages.sort(
            key=lambda t: (
                1 if t[1] is None else 0,
                t[1] if isinstance(t[1], int) else 999999
            )
        )

        if debug:
            print(f"\nCourier {courier} sorted pages (pno, qty): {pages}")

        final_order.extend([p for p, _ in pages])

    if debug:
        print("\nFinal page order:", final_order)

    # 6. Build output document
    out = fitz.open()
    for pno in final_order:
        out.insert_pdf(doc, from_page=pno, to_page=pno)

    return out
    


def extract_orders_from_pdf(doc: fitz.Document, order_ids: list):
    """
    Scan pages and collect mapping order_id -> list of page numbers where the order id appears.
    Returns:
        orders_pages_map: dict(order_id -> sorted list of page indices)
        pages_to_remove: sorted list of unique page indices to remove from original
    """
    orders_pages_map = {oid: [] for oid in order_ids}
    pages_to_remove_set = set()

    for pno in range(len(doc)):
        try:
            page = doc.load_page(pno)
            text = page.get_text("text")  # plain text extraction
        except Exception as e:
            continue

        for oid in order_ids:
            if oid and oid in text:
                # add the page to that order
                orders_pages_map[oid].append(pno)
                pages_to_remove_set.add(pno)

    # filter out orders that had no matches
    orders_pages_map = {oid: sorted(list(pages)) for oid, pages in orders_pages_map.items() if pages}
    pages_to_remove = sorted(list(pages_to_remove_set))
    return orders_pages_map, pages_to_remove

def build_doc_from_pages(src_doc: fitz.Document, pages: list):
    """
    Create a new fitz.Document with pages in `pages` (in that order).
    pages are indices from src_doc.
    """
    new_doc = fitz.open()
    for p in pages:
        new_doc.insert_pdf(src_doc, from_page=p, to_page=p)
    return new_doc

def build_clean_doc(src_doc: fitz.Document, pages_to_remove: list):
    """
    Build a new document with pages not in pages_to_remove.
    """
    pages_to_remove_set = set(pages_to_remove)
    new_doc = fitz.open()
    for i in range(len(src_doc)):
        if i not in pages_to_remove_set:
            new_doc.insert_pdf(src_doc, from_page=i, to_page=i)
    return new_doc
