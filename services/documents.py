"""Генерация PDF-документов: чеки платежей, акты завершения сделок."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fpdf import FPDF

DOCS_DIR = Path("static/uploads/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

_FONT_PATHS = [
    # Windows
    ("C:/Windows/Fonts/arial.ttf",   "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
    ("C:/Windows/Fonts/verdana.ttf", "C:/Windows/Fonts/verdanab.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
     "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    # macOS
    ("/Library/Fonts/Arial.ttf",     "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def _fmt_money(amount: float) -> str:
    return f"{float(amount or 0):,.2f}".replace(",", " ").replace(".", ",") + " руб."


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


class _DocPDF(FPDF):
    _fn = "Helvetica"
    _loaded = False

    def load_fonts(self):
        for reg, bold in _FONT_PATHS:
            try:
                self.add_font("F", "",  reg)
                self.add_font("F", "B", bold)
                self._fn = "F"
                self._loaded = True
                return
            except Exception:
                continue

    def f(self, style=""):
        return self._fn

    def green_header(self, title: str, subtitle: str, doc_id: str):
        # Зелёная шапка
        self.set_fill_color(21, 128, 61)
        self.rect(0, 0, 210, 48, "F")
        self.set_fill_color(16, 185, 129)
        self.rect(0, 44, 210, 4, "F")
        # Лого
        self.set_text_color(255, 255, 255)
        self.set_font(self.f(), "B", 18)
        self.set_xy(14, 8)
        self.cell(0, 10, "StartHub", ln=True)
        # Заголовок
        self.set_font(self.f(), "B", 13)
        self.set_x(14)
        self.cell(0, 8, title, ln=True)
        # Субтитул
        self.set_font(self.f(), "", 9)
        self.set_text_color(200, 240, 220)
        self.set_x(14)
        self.cell(0, 6, subtitle, ln=True)
        # Номер документа справа
        self.set_font(self.f(), "", 8)
        self.set_text_color(180, 230, 200)
        self.set_xy(14, 38)
        self.cell(182, 5, f"Документ: {doc_id}  ·  {_now_str()}", align="R")
        # Сброс
        self.set_text_color(30, 30, 30)
        self.set_y(60)

    def amount_box(self, label: str, amount_str: str):
        self.set_fill_color(240, 253, 244)
        self.set_draw_color(187, 247, 208)
        self.rect(14, self.get_y(), 182, 28, "FD")
        self.set_font(self.f(), "", 9)
        self.set_text_color(107, 114, 128)
        self.set_xy(14, self.get_y() + 5)
        self.cell(182, 5, label, align="C")
        self.set_font(self.f(), "B", 20)
        self.set_text_color(21, 128, 61)
        self.set_x(14)
        self.cell(182, 12, amount_str, align="C")
        self.set_text_color(30, 30, 30)
        self.ln(34)

    def info_table(self, rows: list[tuple[str, str]]):
        self.set_font(self.f(), "B", 9)
        self.set_fill_color(240, 253, 244)
        self.set_draw_color(187, 247, 208)
        self.set_text_color(21, 128, 61)
        self.set_x(14)
        self.cell(72, 7, "Параметр", border="B", fill=True)
        self.cell(110, 7, "Значение", border="B", fill=True, ln=True)
        self.set_text_color(30, 30, 30)
        for i, (k, v) in enumerate(rows):
            self.set_fill_color(247, 253, 250) if i % 2 == 0 else self.set_fill_color(255, 255, 255)
            self.set_font(self.f(), "", 9)
            self.set_x(14)
            self.cell(72, 6, k, border="B", fill=True)
            self.set_font(self.f(), "B" if k == "ИТОГО" else "", 9)
            self.set_text_color(21, 128, 61 if k == "ИТОГО" else 30)
            self.cell(110, 6, str(v)[:55], border="B", fill=True, ln=True)
            self.set_text_color(30, 30, 30)

    def stamp(self, text: str = "ОПЛАЧЕНО"):
        self.set_draw_color(21, 128, 61)
        self.set_text_color(21, 128, 61)
        self.set_font(self.f(), "B", 14)
        cx, cy = 155, self.get_y() + 8
        self.ellipse(cx - 22, cy - 8, 44, 16, "D")
        self.set_xy(cx - 22, cy - 5)
        self.cell(44, 10, text, align="C")
        self.set_text_color(30, 30, 30)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(187, 247, 208)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_font(self.f(), "", 8)
        self.set_text_color(156, 163, 175)
        self.cell(91, 6, "StartHub  ·  starthub33.ru", align="L")
        self.cell(91, 6, _now_str(), align="R")


def generate_receipt_pdf(
    deal_id: int,
    startup_title: str,
    buyer_name: str,
    seller_name: str,
    amount: float,
    method_label: str,
    payment_note: str = "",
) -> str:
    """Генерирует PDF-чек оплаты сделки, сохраняет на диск. Возвращает URL-путь."""
    doc_id = uuid.uuid4().hex[:8].upper()

    pdf = _DocPDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.green_header("КВИТАНЦИЯ ОБ ОПЛАТЕ", "Подтверждение платежа по сделке", doc_id)

    pdf.amount_box("Сумма платежа", _fmt_money(amount))

    rows = [
        ("Стартап", startup_title[:50]),
        ("Сделка №", str(deal_id)),
        ("Продавец", seller_name[:40]),
        ("Покупатель", buyer_name[:40]),
        ("Способ оплаты", method_label),
    ]
    if payment_note:
        rows.append(("Примечание", payment_note[:50]))
    rows.append(("ИТОГО", _fmt_money(amount)))
    pdf.info_table(rows)

    pdf.ln(6)
    pdf.stamp("ОПЛАЧЕНО")

    filename = f"receipt_{deal_id}_{doc_id}.pdf"
    path = DOCS_DIR / filename
    path.write_bytes(bytes(pdf.output()))
    return f"/static/uploads/docs/{filename}"


# Алиас для обратной совместимости
generate_receipt_html = generate_receipt_pdf


def generate_completion_act_pdf(
    deal_id: int,
    startup_title: str,
    buyer_name: str,
    seller_name: str,
    final_amount: float,
) -> str:
    """Генерирует PDF акт завершения сделки. Возвращает URL-путь."""
    doc_id = uuid.uuid4().hex[:8].upper()
    now_date = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    pdf = _DocPDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.green_header(
        "АКТ О ЗАВЕРШЕНИИ СДЕЛКИ",
        f"№ {doc_id}  ·  Дата: {now_date}  ·  Платформа StartHub",
        doc_id,
    )

    # Стороны
    pdf.set_fill_color(240, 253, 244)
    pdf.set_draw_color(187, 247, 208)
    pdf.rect(14, pdf.get_y(), 182, 32, "FD")
    pdf.set_font(pdf.f(), "B", 10)
    pdf.set_text_color(21, 128, 61)
    pdf.set_xy(18, pdf.get_y() + 4)
    pdf.cell(0, 6, "Стороны сделки", ln=True)
    pdf.set_font(pdf.f(), "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.set_x(18)
    pdf.cell(0, 6, f"Продавец: {seller_name[:50]}", ln=True)
    pdf.set_x(18)
    pdf.cell(0, 6, f"Покупатель: {buyer_name[:50]}", ln=True)
    pdf.set_x(18)
    pdf.cell(0, 6, f"Предмет: Стартап \"{startup_title[:45]}\" (Сделка #{deal_id})", ln=True)
    pdf.ln(10)

    # Текст акта
    pdf.set_font(pdf.f(), "", 10)
    pdf.set_x(14)
    pdf.multi_cell(
        182, 6,
        f"Настоящий акт подтверждает, что сделка по отчуждению стартапа "
        f"\"{startup_title}\" между Продавцом и Покупателем завершена в полном объёме. "
        f"Все обязательства сторон исполнены. Претензий стороны друг к другу не имеют.",
        align="J",
    )
    pdf.ln(6)

    pdf.amount_box("Итоговая сумма сделки", _fmt_money(final_amount))

    pdf.set_font(pdf.f(), "", 10)
    pdf.set_x(14)
    pdf.multi_cell(
        182, 6,
        "Настоящий акт составлен на платформе StartHub и имеет силу "
        "двустороннего соглашения об исполнении обязательств.",
        align="J",
    )
    pdf.ln(14)

    # Подписи
    y = pdf.get_y()
    pdf.set_draw_color(100, 100, 100)
    pdf.line(14, y, 95, y)
    pdf.line(115, y, 196, y)
    pdf.set_font(pdf.f(), "", 9)
    pdf.set_text_color(107, 114, 128)
    pdf.set_xy(14, y + 2)
    pdf.cell(81, 5, f"Продавец: {seller_name[:25]}")
    pdf.set_x(115)
    pdf.cell(81, 5, f"Покупатель: {buyer_name[:25]}")
    pdf.set_text_color(30, 30, 30)

    filename = f"act_{deal_id}_{doc_id}.pdf"
    path = DOCS_DIR / filename
    path.write_bytes(bytes(pdf.output()))
    return f"/static/uploads/docs/{filename}"


# Алиас для обратной совместимости
generate_completion_act_html = generate_completion_act_pdf


def generate_wallet_receipt_pdf(
    tx_id: int,
    username: str,
    user_id: int,
    user_email: str,
    amount: float,
    description: str,
    balance_after: float,
) -> bytes:
    """Генерирует PDF чека пополнения кошелька. Возвращает bytes (не сохраняет на диск)."""
    doc_id = f"W{tx_id:06d}"

    pdf = _DocPDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.green_header("ЧЕК ПОПОЛНЕНИЯ КОШЕЛЬКА", "StartHub · Подтверждение операции", doc_id)

    pdf.amount_box("Сумма пополнения", f"+{_fmt_money(amount)}")

    pdf.info_table([
        ("Номер транзакции",  f"#{tx_id}"),
        ("Пользователь",      f"@{username} (ID #{user_id})"),
        ("Email",             user_email[:50]),
        ("Способ пополнения", description[:50]),
        ("Сумма",             _fmt_money(amount)),
        ("Дата и время",      _now_str()),
        ("Баланс после",      _fmt_money(balance_after)),
        ("ИТОГО",             _fmt_money(amount)),
    ])

    pdf.ln(6)
    pdf.stamp("ЗАЧИСЛЕНО")

    return bytes(pdf.output())
