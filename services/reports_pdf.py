"""Генерация PDF-отчётов через fpdf2."""
import io
from datetime import datetime, timezone
from fpdf import FPDF

# Пути к шрифтам (кросс-платформенно)
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


def _money(v) -> str:
    try:
        return f"{float(v or 0):,.0f}".replace(",", " ") + " руб."
    except Exception:
        return "0 руб."


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


class _PDF(FPDF):
    _font = "Helvetica"
    _font_loaded = False

    def load_fonts(self):
        for reg, bold in _FONT_PATHS:
            try:
                self.add_font("CyrFont", "", reg)
                self.add_font("CyrFont", "B", bold)
                self._font = "CyrFont"
                self._font_loaded = True
                return
            except Exception:
                continue

    def f(self, style=""):
        return self._font if self._font_loaded else "Helvetica"

    def header_bar(self, title: str, subtitle: str = ""):
        self.set_fill_color(21, 128, 61)
        self.rect(0, 0, 210, 42, "F")
        # Декор-прямоугольник
        self.set_fill_color(16, 185, 129)
        self.rect(0, 38, 210, 4, "F")
        self.set_text_color(255, 255, 255)
        self.set_font(self.f(), "B", 20)
        self.set_xy(14, 10)
        self.cell(0, 10, "StartHub", ln=True)
        self.set_font(self.f(), "B", 14)
        self.set_x(14)
        self.cell(0, 8, title, ln=True)
        if subtitle:
            self.set_font(self.f(), "", 9)
            self.set_text_color(200, 240, 220)
            self.set_x(14)
            self.cell(0, 6, subtitle, ln=True)
        self.set_text_color(30, 30, 30)
        self.set_y(52)

    def section(self, title: str):
        self.set_fill_color(240, 253, 244)
        self.set_draw_color(187, 247, 208)
        self.set_font(self.f(), "B", 11)
        self.set_text_color(21, 128, 61)
        self.set_x(14)
        self.cell(182, 8, title, border="B", ln=True, fill=True)
        self.set_text_color(30, 30, 30)
        self.ln(3)

    def kpi_row(self, items: list[tuple[str, str]]):
        """Ряд KPI-ячеек. items = [(label, value), ...]"""
        cell_w = 182 / len(items)
        x0 = 14
        for label, value in items:
            self.set_xy(x0, self.get_y())
            self.set_fill_color(240, 253, 244)
            self.set_draw_color(187, 247, 208)
            self.rect(x0, self.get_y(), cell_w - 2, 22, "FD")
            self.set_font(self.f(), "", 8)
            self.set_text_color(107, 114, 128)
            self.set_xy(x0 + 3, self.get_y() + 3)
            self.cell(cell_w - 8, 5, label)
            self.set_font(self.f(), "B", 13)
            self.set_text_color(21, 128, 61)
            self.set_xy(x0 + 3, self.get_y() + 6)
            self.cell(cell_w - 8, 8, value)
            x0 += cell_w
        self.set_text_color(30, 30, 30)
        self.ln(28)

    def table_header(self, cols: list[tuple[str, int]]):
        """cols = [(label, width), ...]"""
        self.set_fill_color(21, 128, 61)
        self.set_text_color(255, 255, 255)
        self.set_font(self.f(), "B", 9)
        self.set_x(14)
        for label, w in cols:
            self.cell(w, 7, label, border=0, fill=True, align="C")
        self.ln()
        self.set_text_color(30, 30, 30)

    def table_row(self, cols: list[tuple[str, int]], fill: bool = False):
        self.set_fill_color(247, 253, 250) if fill else self.set_fill_color(255, 255, 255)
        self.set_draw_color(229, 231, 235)
        self.set_font(self.f(), "", 9)
        self.set_x(14)
        for value, w in cols:
            self.cell(w, 6, str(value)[:40], border="B", fill=True)
        self.ln()

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(187, 247, 208)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_font(self.f(), "", 8)
        self.set_text_color(156, 163, 175)
        self.cell(91, 6, "StartHub · starthub33.ru", align="L")
        self.cell(91, 6, _now(), align="R")


def generate_general_pdf(data: dict) -> bytes:
    pdf = _PDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.header_bar("Общий отчёт платформы", f"Сформирован: {_now()}")

    # KPI
    pdf.section("Ключевые показатели")
    pdf.kpi_row([
        ("Пользователей", str(data["users_total"])),
        ("Стартапов", str(data["startups_total"])),
        ("Сделок", str(data["deals_total"])),
        ("Сумма сделок", _money(data["deals_amount_total"])),
    ])

    # Стартапы
    pdf.section("Стартапы")
    pdf.kpi_row([
        ("Активных", str(data["startups_active"])),
        ("Продано", str(data["startups_sold"])),
        ("Всего", str(data["startups_total"])),
    ])

    # Пользователи по ролям
    pdf.section("Пользователи по ролям")
    pdf.table_header([("Роль", 60), ("Количество", 40), ("Доля, %", 40)])
    total = data["users_total"] or 1
    for i, (role, cnt) in enumerate(data["users_by_role"].items()):
        pct = f"{cnt / total * 100:.1f}%"
        pdf.table_row([(role, 60), (str(cnt), 40), (pct, 40)], fill=i % 2 == 0)
    pdf.ln(4)

    # Финансы
    pdf.section("Финансовая сводка")
    pdf.table_header([("Показатель", 120), ("Значение", 62)])
    rows = [
        ("Пополнений кошельков (сумма)", _money(data["deposits_total"])),
        ("Пополнений кошельков (кол-во)", str(data["deposits_count"])),
        ("Сумма закрытых сделок", _money(data["deals_amount_total"])),
    ]
    for i, (k, v) in enumerate(rows):
        pdf.table_row([(k, 120), (v, 62)], fill=i % 2 == 0)

    return bytes(pdf.output())


def generate_deals_pdf(data: dict) -> bytes:
    pdf = _PDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.header_bar("Отчёт по сделкам", f"Последние {len(data['recent_deals'])} сделок · {_now()}")

    # Сделки по статусам
    pdf.section("Сделки по статусам")
    pdf.table_header([("Статус", 70), ("Количество", 50), ("Доля, %", 40)])
    total = data["deals_total"] or 1
    for i, (status, cnt) in enumerate(data["deals_by_status"].items()):
        pct = f"{cnt / total * 100:.1f}%"
        pdf.table_row([(status, 70), (str(cnt), 50), (pct, 40)], fill=i % 2 == 0)
    pdf.ln(4)

    # Таблица последних сделок
    pdf.section("Список последних сделок")
    cols = [("#", 12), ("Стартап", 52), ("Покупатель", 38), ("Статус", 28), ("Сумма", 32), ("Дата", 20)]
    pdf.table_header(cols)
    for i, d in enumerate(data["recent_deals"]):
        amount = _money(d.final_amount or d.amount) if (d.final_amount or d.amount) else "—"
        date = d.created_at.strftime("%d.%m.%y") if d.created_at else "—"
        buyer = (d.buyer.full_name or d.buyer.username)[:18]
        pdf.table_row([
            (str(d.id), 12),
            (d.startup.title[:28], 52),
            (buyer, 38),
            (d.status.value, 28),
            (amount, 32),
            (date, 20),
        ], fill=i % 2 == 0)

    return bytes(pdf.output())


def generate_financial_pdf(data: dict) -> bytes:
    pdf = _PDF()
    pdf.load_fonts()
    pdf.add_page()
    pdf.header_bar("Финансовый отчёт", f"Сформирован: {_now()}")

    # Ключевые цифры
    pdf.section("Финансовые показатели")
    pdf.kpi_row([
        ("Пополнений (сумма)", _money(data["deposits_total"])),
        ("Пополнений (кол-во)", str(data["deposits_count"])),
    ])
    pdf.kpi_row([
        ("Сумма закрытых сделок", _money(data["deals_amount_total"])),
        ("Успешных сделок", str(data["deals_by_status"].get("closed_ok", 0))),
    ])

    # Таблица по статусам
    pdf.section("Сделки по статусам")
    pdf.table_header([("Статус", 80), ("Количество", 50), ("Доля, %", 52)])
    total = data["deals_total"] or 1
    for i, (status, cnt) in enumerate(data["deals_by_status"].items()):
        pct = f"{cnt / total * 100:.1f}%"
        pdf.table_row([(status, 80), (str(cnt), 50), (pct, 52)], fill=i % 2 == 0)
    pdf.ln(4)

    # Топ стартапов
    if data["top_startups"]:
        pdf.section("Топ стартапов по сделкам")
        pdf.table_header([("#", 12), ("Стартап", 130), ("Сделок", 40)])
        for i, s in enumerate(data["top_startups"]):
            pdf.table_row([(str(i + 1), 12), (s.title[:60], 130), (str(s.deals_count), 40)], fill=i % 2 == 0)

    return bytes(pdf.output())
