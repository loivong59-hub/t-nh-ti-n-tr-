import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# =========================================================
# CẤU HÌNH ỨNG DỤNG
# =========================================================
st.set_page_config(
    page_title="Quản lý tiền phòng trọ",
    page_icon="🏠",
    layout="wide",
)

DB_PATH = Path(__file__).with_name("quan_ly_tien_tro.db")
DEFAULTS = {
    "gia_dien": 3500,
    "gia_nuoc": 15000,
    "phi_khac": 150000,
    "so_phong": 10,
}


# =========================================================
# SQLITE
# =========================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS room_monthly (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                room_number INTEGER NOT NULL,
                tenant_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                rent INTEGER NOT NULL DEFAULT 2500000,
                electric_old INTEGER NOT NULL DEFAULT 0,
                electric_new INTEGER NOT NULL DEFAULT 0,
                water_old INTEGER NOT NULL DEFAULT 0,
                water_new INTEGER NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'Chưa thanh toán',
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (year, month, room_number)
            )
        """)
        for key, value in DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(setting_key, setting_value) VALUES (?, ?)",
                (key, str(value)),
            )


def get_setting(key):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
        ).fetchone()
    return row["setting_value"] if row else str(DEFAULTS[key])


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO settings(setting_key, setting_value) VALUES (?, ?)
ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
        """, (key, str(value)))


def fetch_room(year, month, room_number):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM room_monthly
            WHERE year = ? AND month = ? AND room_number = ?
        """, (year, month, room_number)).fetchone()
    return dict(row) if row else None


def fetch_month(year, month, room_count):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM room_monthly
            WHERE year = ? AND month = ? AND room_number BETWEEN 1 AND ?
            ORDER BY room_number
        """, (year, month, room_count)).fetchall()
    return {row["room_number"]: dict(row) for row in rows}


def previous_meter_readings(year, month, room_number):
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    previous = fetch_room(prev_year, prev_month, room_number)
    if previous:
        return int(previous["electric_new"]), int(previous["water_new"])
    return 0, 0


def ensure_month_rooms(year, month, room_count):
    """Tạo bản ghi cho phòng chưa có trong kỳ; chỉ số cũ kế thừa kỳ trước."""
    with get_connection() as conn:
        for room_number in range(1, room_count + 1):
            exists = conn.execute("""
                SELECT 1 FROM room_monthly
                WHERE year = ? AND month = ? AND room_number = ?
            """, (year, month, room_number)).fetchone()
            if exists:
                continue

            electric_old, water_old = previous_meter_readings(
                year, month, room_number
            )
            conn.execute("""
                INSERT INTO room_monthly
                (year, month, room_number, tenant_name, phone, rent,
                 electric_old, electric_new, water_old, water_new,
                 payment_status, note)
                VALUES (?, ?, ?, '', '', 2500000, ?, ?, ?, ?,
                        'Chưa thanh toán', '')
            """, (
                year, month, room_number,
                electric_old, electric_old, water_old, water_old
            ))


def save_room(record):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO room_monthly (
                year, month, room_number, tenant_name, phone, rent,
                electric_old, electric_new, water_old, water_new,
                payment_status, note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(year, month, room_number) DO UPDATE SET
                tenant_name = excluded.tenant_name,
                phone = excluded.phone,
                rent = excluded.rent,
                electric_old = excluded.electric_old,
electric_new = excluded.electric_new,
                water_old = excluded.water_old,
                water_new = excluded.water_new,
                payment_status = excluded.payment_status,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
        """, (
            record["year"], record["month"], record["room_number"],
            record["tenant_name"], record["phone"], record["rent"],
            record["electric_old"], record["electric_new"],
            record["water_old"], record["water_new"],
            record["payment_status"], record["note"],
        ))


init_db()

# =========================================================
# SIDEBAR - CẤU HÌNH
# =========================================================
st.title("🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ – VŨ ĐỨC BÌNH")
st.caption("Dữ liệu được lưu tự động vào cơ sở dữ liệu SQLite trên máy chạy ứng dụng.")

st.sidebar.header("⚙️ Đơn giá điện nước")
gia_dien = st.sidebar.number_input(
    "⚡ Giá điện (đ/kWh)", min_value=0,
    value=int(get_setting("gia_dien")), step=100, key="setting_gia_dien"
)
gia_nuoc = st.sidebar.number_input(
    "💧 Giá nước (đ/m³)", min_value=0,
    value=int(get_setting("gia_nuoc")), step=500, key="setting_gia_nuoc"
)
phi_khac = st.sidebar.number_input(
    "📦 Phí khác (wifi, vệ sinh...)", min_value=0,
    value=int(get_setting("phi_khac")), step=10000, key="setting_phi_khac"
)
so_phong = st.sidebar.slider(
    "Số lượng phòng", min_value=1, max_value=100,
    value=int(get_setting("so_phong")), step=1, key="setting_so_phong"
)

set_setting("gia_dien", gia_dien)
set_setting("gia_nuoc", gia_nuoc)
set_setting("phi_khac", phi_khac)
set_setting("so_phong", so_phong)

st.sidebar.divider()
st.sidebar.subheader("📅 Kỳ thu tiền")
now = datetime.now()
col_year, col_month = st.sidebar.columns(2)
with col_year:
    years = list(range(now.year - 3, now.year + 6))
    year = st.selectbox("Năm", years, index=years.index(now.year))
with col_month:
    month = st.selectbox(
        "Tháng", list(range(1, 13)),
        index=now.month - 1, format_func=lambda m: f"Tháng {m}"
    )

ensure_month_rooms(year, month, so_phong)
month_data = fetch_month(year, month, so_phong)

# =========================================================
# NHẬP THÔNG TIN PHÒNG
# =========================================================
st.header(f"📋 Nhập số liệu – Tháng {month}/{year}")
room_number = st.selectbox(
    "Chọn phòng cần cập nhật",
    options=list(range(1, so_phong + 1)),
    format_func=lambda x: f"Phòng {x}",
    key=f"room_select_{year}_{month}_{so_phong}",
)

room = fetch_room(year, month, room_number)
if room is None:
    st.error("Không tìm thấy dữ liệu phòng. Hãy tải lại trang.")
    st.stop()

st.subheader(f"🏠 Cập nhật Phòng {room_number}")
with st.form(key=f"room_form_{year}_{month}_{room_number}"):
# Người ở và giá phòng cùng một hàng
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        tenant_name = st.text_input("👤 Họ tên người ở", value=room["tenant_name"])
    with c2:
        phone = st.text_input("📞 Số điện thoại", value=room["phone"])
    with c3:
        rent = st.number_input(
            "💵 Giá phòng (VNĐ)", min_value=0,
            value=int(room["rent"]), step=50000
        )

    c4, c5, c6, c7 = st.columns(4)
    with c4:
        electric_old = st.number_input(
            "⚡ Số điện CŨ", min_value=0, value=int(room["electric_old"]), step=1
        )
    with c5:
        electric_new = st.number_input(
            "⚡ Số điện MỚI", min_value=0, value=int(room["electric_new"]), step=1
        )
    with c6:
        water_old = st.number_input(
            "💧 Số nước CŨ", min_value=0, value=int(room["water_old"]), step=1
        )
    with c7:
        water_new = st.number_input(
            "💧 Số nước MỚI", min_value=0, value=int(room["water_new"]), step=1
        )

    payment_status = st.selectbox(
        "💳 Trạng thái thanh toán",
        options=["Chưa thanh toán", "Đã thanh toán"],
        index=["Chưa thanh toán", "Đã thanh toán"].index(room["payment_status"])
        if room["payment_status"] in ["Chưa thanh toán", "Đã thanh toán"] else 0,
    )
    note = st.text_area(
        "📝 Ghi chú thêm (không bắt buộc)",
        value=room["note"],
        placeholder="Ví dụ: Hẹn thanh toán ngày 10..."
    )
    submitted = st.form_submit_button("💾 Lưu thông tin phòng", type="primary", use_container_width=True)

if submitted:
    if electric_new < electric_old:
        st.warning("Số điện mới nhỏ hơn số điện cũ. Tiền điện sẽ được tính là 0 cho đến khi bạn chỉnh lại.")
    if water_new < water_old:
        st.warning("Số nước mới nhỏ hơn số nước cũ. Tiền nước sẽ được tính là 0 cho đến khi bạn chỉnh lại.")
    save_room({
        "year": year,
        "month": month,
        "room_number": room_number,
        "tenant_name": tenant_name.strip(),
        "phone": phone.strip(),
        "rent": int(rent),
        "electric_old": int(electric_old),
        "electric_new": int(electric_new),
        "water_old": int(water_old),
        "water_new": int(water_new),
        "payment_status": payment_status,
        "note": note.strip(),
    })
    st.success(f"Đã lưu dữ liệu Phòng {room_number} vào SQLite.")
    st.rerun()

# =========================================================
# TÍNH TOÁN VÀ BẢNG TỔNG HỢP
# =========================================================
def calculate(row):
    electric_used = max(int(row["electric_new"]) - int(row["electric_old"]), 0)
    water_used = max(int(row["water_new"]) - int(row["water_old"]), 0)
    electric_cost = electric_used * int(gia_dien)
    water_cost = water_used * int(gia_nuoc)
    total = int(row["rent"]) + electric_cost + water_cost + int(phi_khac)
    return electric_used, water_used, electric_cost, water_cost, total


def money(value):
    return f"{int(value):,}".replace(",", ".") + " đ"


rows = []
total_revenue = 0
unpaid_total = 0
paid_count = 0
unpaid_count = 0

# Refresh from database after any save
month_data = fetch_month(year, month, so_phong)
for number in range(1, so_phong + 1):
    row = month_data.get(number)
    if not row:
        continue
    used_e, used_w, cost_e, cost_w, total = calculate(row)
    total_revenue += total
    if row["payment_status"] == "Đã thanh toán":
        paid_count += 1
    else:
        unpaid_count += 1
        unpaid_total += total

    rows.append({
        "Phòng": f"Phòng {number}",
        "Người ở": row["tenant_name"],
        "Số điện cũ": row["electric_old"],
        "Số điện mới": row["electric_new"],
        "Tiền điện (đ)": cost_e,
        "Số nước cũ": row["water_old"],
        "Số nước mới": row["water_new"],
        "Tiền nước (đ)": cost_w,
        "Giá phòng (đ)": row["rent"],
        "Phí khác (đ)": int(phi_khac),
        "Tổng tiền (đ)": total,
        "Trạng thái": row["payment_status"],
        "Ghi chú": row["note"],
    })

st.divider()
st.header(f"📊 Bảng tổng hợp tiền trọ – Tháng {month}/{year}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Tổng tiền dự kiến", money(total_revenue))
m2.metric("Tổng tiền chưa thu", money(unpaid_total))
m3.metric("Đã thanh toán", f"{paid_count} phòng")
m4.metric("Chưa thanh toán", f"{unpaid_count} phòng")

if rows:
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Chưa có dữ liệu phòng trong kỳ này.")

# =========================================================
# XUẤT HÓA ĐƠN PDF THEO TỪNG PHÒNG
# =========================================================
def register_vietnamese_font():
    """Tìm font Unicode để PDF hiển thị tiếng Việt có dấu."""
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("VietnameseFont", regular))
            if Path(bold).exists():
                pdfmetrics.registerFont(TTFont("VietnameseFont-Bold", bold))
            else:
                pdfmetrics.registerFont(TTFont("VietnameseFont-Bold", regular))
            return "VietnameseFont", "VietnameseFont-Bold"
    return "Helvetica", "Helvetica-Bold"
def create_room_pdf(row, year, month, electric_price, water_price, other_fee):
    regular_font, bold_font = register_vietnamese_font()
    used_e, used_w, cost_e, cost_w, total = calculate(row)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Hoa don tien phong {row['room_number']} - {month}/{year}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "VietnameseTitle", parent=styles["Title"],
        fontName=bold_font, fontSize=17, leading=22,
        alignment=1, textColor=colors.HexColor("#163A5F"),
        spaceAfter=8,
    )
    normal = ParagraphStyle(
        "VietnameseNormal", parent=styles["Normal"],
        fontName=regular_font, fontSize=10, leading=15,
    )
    section = ParagraphStyle(
        "VietnameseSection", parent=styles["Heading2"],
        fontName=bold_font, fontSize=11, leading=15,
        textColor=colors.HexColor("#163A5F"), spaceBefore=8, spaceAfter=5,
    )

    story = [
        Paragraph("PHIẾU THU TIỀN PHÒNG TRỌ", title_style),
        Paragraph(f"Kỳ thanh toán: Tháng {month}/{year}", normal),
        Spacer(1, 5 * mm),
        Paragraph("THÔNG TIN NGƯỜI THUÊ", section),
        Paragraph(f"<b>Phòng:</b> {row['room_number']}", normal),
        Paragraph(f"<b>Họ tên:</b> {row['tenant_name'] or 'Chưa cập nhật'}", normal),
        Paragraph(f"<b>Số điện thoại:</b> {row['phone'] or 'Chưa cập nhật'}", normal),
        Spacer(1, 4 * mm),
        Paragraph("CHI TIẾT CHI PHÍ", section),
    ]

    table_data = [
        ["Khoản thu", "Cách tính", "Thành tiền"],
        ["Tiền phòng", "Theo giá phòng tháng", money(row["rent"])],
        ["Tiền điện", f"{used_e} kWh × {money(electric_price)}", money(cost_e)],
        ["Tiền nước", f"{used_w} m³ × {money(water_price)}", money(cost_w)],
        ["Phí khác", "Wifi, vệ sinh...", money(other_fee)],
        ["TỔNG CỘNG", "", money(total)],
    ]
    table = Table(table_data, colWidths=[42 * mm, 75 * mm, 43 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular_font),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, -1), (-1, -1), bold_font),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F1F8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C5D3")),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        table,
        Spacer(1, 6 * mm),
Paragraph(
            f"<b>Trạng thái thanh toán:</b> {row['payment_status']}",
            normal
        ),
    ])
    if row["note"]:
        story.append(Paragraph(f"<b>Ghi chú:</b> {row['note']}", normal))
    story.extend([
        Spacer(1, 14 * mm),
        Paragraph("Người thu tiền", normal),
        Spacer(1, 18 * mm),
        Paragraph("(Ký và ghi rõ họ tên)", normal),
    ])
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


st.divider()
st.header("📄 Xuất phiếu thu PDF theo từng phòng")
pdf_room = st.selectbox(
    "Chọn phòng cần xuất PDF",
    options=list(range(1, so_phong + 1)),
    format_func=lambda x: f"Phòng {x}",
    key=f"pdf_room_{year}_{month}_{so_phong}",
)
pdf_data = fetch_room(year, month, pdf_room)
if pdf_data:
    _, _, _, _, pdf_total = calculate(pdf_data)
    st.caption(
        f"Phòng {pdf_room} · {pdf_data['tenant_name'] or 'Chưa cập nhật người ở'} "
        f"· Tổng tiền: {money(pdf_total)} · {pdf_data['payment_status']}"
    )
    pdf_bytes = create_room_pdf(pdf_data, year, month, gia_dien, gia_nuoc, phi_khac)
    st.download_button(
        label=f"📥 Tải phiếu thu PDF – Phòng {pdf_room}",
        data=pdf_bytes,
        file_name=f"Phieu_Thu_Phong_{pdf_room}_Thang_{month}_{year}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

st.caption(f"Database: {DB_PATH.name} · Đơn giá được lưu trong SQLite.")
