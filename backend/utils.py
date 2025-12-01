import fitz  # PyMuPDF
from PIL import Image
import io
from pathlib import Path
from typing import List
from datetime import datetime
import pytz
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO
from typing import List, Dict
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch



def remove_pdf_whitespace(doc: fitz.Document, dpi: int = 150):
    scale = dpi / 72
    out = fitz.open()

    for pno in range(len(doc)):
        page = doc[pno]

        words = page.get_text("words")
        if words:
            x0 = min(w[0] for w in words)
            y0 = min(w[1] for w in words)
            x1 = max(w[2] for w in words)
            y1 = max(w[3] for w in words)
            bbox = fitz.Rect(x0, y0, x1, y1)
        else:
            blocks = page.get_text("dict").get("blocks", [])
            rects = [fitz.Rect(b["bbox"]) for b in blocks]
            bbox = sum(rects, rects[0]) if rects else page.rect

        margin = 4
        clip = fitz.Rect(
            bbox.x0 - margin,
            bbox.y0 - margin,
            bbox.x1 + margin,
            bbox.y1 + margin
        )

        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        new_page = out.new_page(width=clip.width, height=clip.height)
        new_page.insert_image(fitz.Rect(0, 0, clip.width, clip.height),
                              stream=img_bytes.read())

    return out




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
