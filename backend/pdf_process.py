from utils import _detect_courier, _extract_quantity
from utils import *
import fitz

# PDF Processor Utility Functions

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

        if extracted_data:
            order_summary = create_order_summary(extracted_data)
            courier_summary = create_courier_summary(extracted_data)
            company_summary = create_company_summary(extracted_data)

            summary_pdf_buffer = create_pdf_report(
                order_summary, courier_summary, company_summary
            )
            summary_doc = fitz.open(stream=summary_pdf_buffer, filetype="pdf")
            final_doc.insert_pdf(summary_doc)

    return final_doc
