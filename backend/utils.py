import fitz  # PyMuPDF
from PIL import Image
import io
from pathlib import Path
from typing import List
from datetime import datetime
import pytz


def get_indian_datetime():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    return now.strftime("%d-%m-%Y %I:%M %p") 



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

remove_pdf_whitespace("white.pdf")


def merge_pdfs(input_pdf_list: List[str], output_pdf_path: str = "merged.pdf") -> str:
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


merge_pdfs([
    "white.pdf",
    "d-21.pdf",
    "g-21.pdf"
])


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

print_datetime_on_label("white.pdf")




