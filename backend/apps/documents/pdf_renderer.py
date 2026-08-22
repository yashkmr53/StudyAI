"""NoteSpace PDF renderer (architecture §7, §49).

FAITHFUL RENDERING CONTRACT:
- input is exactly the DocumentLine texts of specific revisions
- output preserves every line verbatim, in source order
- headings are styled only when explicitly flagged (is_heading)
- the renderer adds NO semantic content — no summaries, corrections,
  or explanations. Structural furniture (page numbers, document title
  metadata) is permitted by §49.

Unicode: DejaVu Sans is vendored (assets/fonts, license-permitted) so
arbitrary transcribed text renders verbatim; core fonts would reject
non-latin-1 characters outright.
"""
import logging
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REGULAR = FONT_DIR / "DejaVuSans.ttf"
BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"


def _fonts_available() -> bool:
    return REGULAR.exists() and BOLD.exists()


class NoteSpacePDF(FPDF):
    def __init__(self, document_title: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._unicode_fonts = _fonts_available()
        if self._unicode_fonts:
            self.add_font("DejaVu", "", str(REGULAR))
            self.add_font("DejaVu", "B", str(BOLD))
            self._body_family = "DejaVu"
        else:
            logger.warning("Vendored DejaVu fonts missing; PDF text limited to latin-1.")
            self._body_family = "helvetica"

        self.document_title = document_title
        self.set_title(document_title)
        self.set_creator("StudyAI NoteSpace")
        self.set_author("StudyAI")
        self.set_subject("Digitized notes (faithful transcription)")
        self.alias_nb_pages("{nb}")
        self.add_page()

    def set_body_font(self, style: str = "", size: float = 11) -> None:
        if self._unicode_fonts:
            self.set_font(self._body_family, style, size)
        else:
            # helvetica supports "" B I BI styles natively
            self.set_font("helvetica", style or "", size)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_body_font(style="", size=8)
        self.cell(0, 10, f"{self.document_title} - Page {self.page_no()} of {{nb}}", align="C")


def render_pdf(pages: list[dict], document_title: str) -> bytes:
    """pages: [{page_number:int, lines:[{text,is_heading?}]}] in page order.

    Returns PDF bytes. Content is emitted verbatim; styling differs only
    for explicitly flagged headings.
    """
    pdf = NoteSpacePDF(document_title=document_title)

    for page_index, page in enumerate(pages):
        if page_index > 0:
            pdf.add_page()
        pdf.set_body_font()
        lines = page["lines"]
        if not lines:
            pdf.multi_cell(0, 6, "(blank page)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            continue
        for line in lines:
            if line.get("is_heading"):
                pdf.set_body_font(style="B", size=14)
                pdf.ln(2)
                pdf.multi_cell(0, 8, line["text"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
                pdf.set_body_font()
            else:
                pdf.multi_cell(0, 6, line["text"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
