
import sqlite3
import io
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# =====================================================
# CẤU HÌNH ỨNG DỤNG
# =====================================================

st.set_page_config(
    page_title="Quản lý tiền phòng trọ",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ VŨ ĐỨC BÌNH")

DB_PATH = Path(__file__).resolve().parent / "quan_ly_tien_tro.db"

TRANG_THAI = ["Chưa thanh toán", "Đã thanh toán"]


# =====================================================
# KẾT NỐI VÀ KHỞI TẠO SQLITE
# =====================================================

def ket_noi_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def khoi_tao_database():
    with ket_noi_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tien_phong (
                nam INTEGER NOT NULL,
                thang INTEGER NOT NULL,
                phong INTEGER NOT NULL,
                nguoi_o TEXT NOT NULL DEFAULT '',
                gia_phong INTEGER NOT NULL DEFAULT 2500000,
                dien_cu INTEGER NOT NULL DEFAULT 0,
                dien_moi INTEGER NOT NULL DEFAULT 0,
                nuoc_cu INTEGER NOT NULL DEFAULT 0,
                nuoc_moi INTEGER NOT NULL DEFAULT 0,
                trang_thai TEXT NOT NULL DEFAULT 'Chưa thanh toán',
                ngay_cap_nhat TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (nam, thang, phong)
            )
        """)

        # Bảo đảm an toàn khi dữ liệu có trạng thái không hợp lệ.
        conn.execute("""
            UPDATE tien_phong
            SET trang_thai = 'Chưa thanh toán'
            WHERE trang_thai NOT IN ('Đã thanh toán', 'Chưa thanh toán')
        """)


def doc_phong(nam, thang, phong):
    with ket_noi_db() as conn:
        row = conn.execute("""
            SELECT * FROM tien_phong
            WHERE nam = ? AND thang = ? AND phong = ?
        """, (nam, thang, phong)).fetchone()

    return dict(row) if row else None


def doc_cac_phong(nam, thang, so_phong):
    with ket_noi_db() as conn:
        rows = conn.execute("""
            SELECT * FROM tien_phong
            WHERE nam = ? AND thang = ? AND phong BETWEEN 1 AND ?
            ORDER BY phong
        """, (nam, thang, so_phong)).fetchall()

    return [dict(row) for row in rows]


def luu_phong(data):
    with ket_noi_db() as conn:
        conn.execute("""
            INSERT INTO tien_phong (
                nam, thang, phong, nguoi_o, gia_phong,
                dien_cu, dien_moi, nuoc_cu, nuoc_moi,
                trang_thai, ngay_cap_nhat
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nam, thang, phong) DO UPDATE SET
                nguoi_o = excluded.nguoi_o,
                gia_phong = excluded.gia_phong,
                dien_cu = excluded.dien_cu,
                dien_moi = excluded.dien_moi,
                nuoc_cu = excluded.nuoc_cu,
                nuoc_moi = excluded.nuoc_moi,
                trang_thai = excluded.trang_thai,
                ngay_cap_nhat = excluded.ngay_cap_nhat
        """, (
            data["nam"],
            data["thang"],
            data["phong"],
            data["nguoi_o"],
            data["gia_phong"],
            data["dien_cu"],
            data["dien_moi"],
            data["nuoc_cu"],
            data["nuoc_moi"],
            data["trang_thai"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))


def lay_chi_so_thang_truoc(nam, thang, phong):
    if thang == 1:
        nam_truoc, thang_truoc = nam - 1, 12
    else:
        nam_truoc, thang_truoc = nam, thang - 1

    data_truoc = doc_phong(nam_truoc, thang_truoc, phong)

    if data_truoc:
        return (
            int(data_truoc["dien_moi"]),
            int(data_truoc["nuoc_moi"]),
        )

    return 0, 0


def khoi_tao_phong_thang(nam, thang, so_phong):
    """Tạo bản ghi cho phòng chưa có trong kỳ, không ghi đè dữ liệu cũ."""
    with ket_noi_db() as conn:
        for phong in range(1, so_phong + 1):
            ton_tai = conn.execute("""
                SELECT 1 FROM tien_phong
                WHERE nam = ? AND thang = ? AND phong = ?
            """, (nam, thang, phong)).fetchone()

            if ton_tai:
                continue

            # Chỉ kế thừa số mới của tháng trước khi tạo kỳ mới.
            dien_cu, nuoc_cu = lay_chi_so_thang_truoc(
                nam, thang, phong
            )

            conn.execute("""
                INSERT INTO tien_phong (
                    nam, thang, phong, nguoi_o, gia_phong,
                    dien_cu, dien_moi, nuoc_cu, nuoc_moi,
                    trang_thai, ngay_cap_nhat
                )
                VALUES (?, ?, ?, '', 2500000, ?, ?, ?, ?,
                        'Chưa thanh toán', ?)
            """, (
                nam,
                thang,
                phong,
                dien_cu,
                dien_cu,
                nuoc_cu,
                nuoc_cu,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))


# =====================================================
# TÍNH TIỀN PHÒNG
# =====================================================

def tinh_tien(data, gia_dien, gia_nuoc, phi_khac):
    so_dien = max(int(data["dien_moi"]) - int(data["dien_cu"]), 0)
    so_nuoc = max(int(data["nuoc_moi"]) - int(data["nuoc_cu"]), 0)

    tien_dien = so_dien * gia_dien
    tien_nuoc = so_nuoc * gia_nuoc
    tong_tien = (
        int(data["gia_phong"]) + tien_dien + tien_nuoc + phi_khac
    )

    return {
        "so_dien": so_dien,
        "so_nuoc": so_nuoc,
        "tien_dien": tien_dien,
        "tien_nuoc": tien_nuoc,
        "phi_khac": phi_khac,
        "tong_tien": tong_tien,
    }


def dinh_dang_tien(value):
    return f"{int(value):,}".replace(",", ".") + " đ"


# =====================================================
# FONT PDF HỖ TRỢ TIẾNG VIỆT
# =====================================================

def dang_ky_font_pdf():
    """Ưu tiên font trong thư mục ứng dụng, sau đó tìm font hệ thống."""
    thu_muc_app = Path(__file__).resolve().parent

    font_thuong = [
        thu_muc_app / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]

    font_dam = [
        thu_muc_app / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]

    path_thuong = next((p for p in font_thuong if p.exists()), None)
    path_dam = next((p for p in font_dam if p.exists()), None)

    if not path_thuong:
        raise FileNotFoundError(
            "Không tìm thấy font Unicode. Hãy tải DejaVuSans.ttf "
            "và đặt cạnh file app.py."
        )

    pdfmetrics.registerFont(TTFont("Vietnamese", str(path_thuong)))

    if path_dam:
        pdfmetrics.registerFont(TTFont("Vietnamese-Bold", str(path_dam)))
        return "Vietnamese", "Vietnamese-Bold"

    return "Vietnamese", "Vietnamese"


# =====================================================
# TẠO PDF RIÊNG CHO MỘT PHÒNG
# =====================================================

def tao_pdf_phong(data, gia_dien, gia_nuoc, phi_khac):
    font_thuong, font_dam = dang_ky_font_pdf()
    tien = tinh_tien(data, gia_dien, gia_nuoc, phi_khac)

    buffer = io.BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Hoa don tien phong {data['phong']}",
        author="Vũ Đức Bình",
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="TieuDeViet",
        fontName=font_dam,
        fontSize=16,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    ))

    styles.add(ParagraphStyle(
        name="NoiDungViet",
        fontName=font_thuong,
        fontSize=10,
        leading=15,
    ))

    styles.add(ParagraphStyle(
        name="NhoViet",
        fontName=font_thuong,
        fontSize=9,
        leading=13,
    ))

    thang_nam = f"{int(data['thang']):02d}/{data['nam']}"

    story = [
        Paragraph("PHIẾU THU TIỀN PHÒNG TRỌ", styles["TieuDeViet"]),
        Paragraph(
            f"<b>Dãy trọ:</b> Vũ Đức Bình<br/>"
            f"<b>Phòng:</b> {data['phong']}<br/>"
            f"<b>Kỳ thanh toán:</b> Tháng {thang_nam}<br/>"
            f"<b>Người ở:</b> {data['nguoi_o'] or 'Chưa cập nhật'}<br/>"
            f"<b>Trạng thái:</b> {data['trang_thai']}",
            styles["NoiDungViet"],
        ),
        Spacer(1, 6 * mm),
    ]

    bang_du_lieu = [
        ["Khoản thu", "Chi tiết", "Thành tiền (VNĐ)"],
        ["Tiền phòng", "Giá phòng tháng", f"{data['gia_phong']:,}"],
        [
            "Tiền điện",
            f"{data['dien_cu']} → {data['dien_moi']} "
            f"({tien['so_dien']} kWh × {gia_dien:,})",
            f"{tien['tien_dien']:,}",
        ],
        [
            "Tiền nước",
            f"{data['nuoc_cu']} → {data['nuoc_moi']} "
            f"({tien['so_nuoc']} m³ × {gia_nuoc:,})",
            f"{tien['tien_nuoc']:,}",
        ],
        ["Phí khác", "Wifi, vệ sinh và các khoản khác", f"{phi_khac:,}"],
        ["TỔNG CỘNG", "", f"{tien['tong_tien']:,}"],
    ]

    bang = Table(
        bang_du_lieu,
        colWidths=[35 * mm, 83 * mm, 48 * mm],
        repeatRows=1,
    )

    bang.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_thuong),
        ("FONTNAME", (0, 0), (-1, 0), font_dam),
        ("FONTNAME", (0, -1), (-1, -1), font_dam),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2F0D9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.extend([
        bang,
        Spacer(1, 8 * mm),
        Paragraph(
            f"<b>Số tiền cần thanh toán: "
            f"{dinh_dang_tien(tien['tong_tien'])}</b>",
            styles["NoiDungViet"],
        ),
        Spacer(1, 15 * mm),
    ])

    bang_ky = Table(
        [[
            Paragraph("Người thuê<br/><br/><br/>"
                      "(Ký và ghi rõ họ tên)", styles["NhoViet"]),
            Paragraph("Người thu tiền<br/><br/><br/>"
                      "(Ký và ghi rõ họ tên)", styles["NhoViet"]),
        ]],
        colWidths=[83 * mm, 83 * mm],
    )
    bang_ky.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(bang_ky)

    pdf.build(story)
    return buffer.getvalue()


# =====================================================
# KHỞI ĐỘNG DATABASE
# =====================================================

khoi_tao_database()


# =====================================================
# SIDEBAR: ĐƠN GIÁ VÀ THỜI GIAN
# =====================================================

st.sidebar.header("⚙️ ĐƠN GIÁ ĐIỆN NƯỚC")

gia_dien = st.sidebar.number_input(
    "⚡ Giá điện (đ/kWh)",
    min_value=0,
    value=3500,
    step=100,
    key="gia_dien",
)

gia_nuoc = st.sidebar.number_input(
    "💧 Giá nước (đ/m³)",
    min_value=0,
    value=15000,
    step=500,
    key="gia_nuoc",
)

phi_khac = st.sidebar.number_input(
    "📦 Phí khác (wifi, vệ sinh...)",
    min_value=0,
    value=150000,
    step=10000,
    key="phi_khac",
)

so_phong = st.sidebar.slider(
    "Số lượng phòng",
    min_value=1,
    max_value=100,
    value=10,
    step=1,
)

st.sidebar.caption(
    "Đơn giá được áp dụng khi tính toán kỳ đang xem. "
    "Hãy xuất báo cáo nếu cần lưu lại số tiền theo đơn giá hiện tại."
)

col_nam, col_thang = st.sidebar.columns(2)

nam_hien_tai = datetime.now().year
danh_sach_nam = list(range(nam_hien_tai - 1, nam_hien_tai + 6))

with col_nam:
    nam_chon = st.selectbox(
        "Chọn năm:",
        danh_sach_nam,
        index=danh_sach_nam.index(nam_hien_tai),
        key="nam_chon",
    )

with col_thang:
    thang_chon = st.selectbox(
        "Chọn tháng:",
        list(range(1, 13)),
        index=datetime.now().month - 1,
        format_func=lambda x: f"Tháng {x}",
        key="thang_chon",
    )

ky_hien_tai = f"Tháng {thang_chon}/{nam_chon}"

# Tạo các bản ghi chưa có, giữ nguyên bản ghi đã tồn tại.
khoi_tao_phong_thang(nam_chon, thang_chon, so_phong)


# =====================================================
# GIAO DIỆN NHẬP VÀ CẬP NHẬT PHÒNG
# =====================================================

st.header(f"📋 Nhập số liệu - {ky_hien_tai}")

phong = st.selectbox(
    "Chọn phòng cần cập nhật:",
    list(range(1, so_phong + 1)),
    format_func=lambda x: f"Phòng {x}",
    key=f"chon_phong_{nam_chon}_{thang_chon}",
)

data = doc_phong(nam_chon, thang_chon, phong)

st.subheader(f"🏠 Cập nhật Phòng {phong} - {ky_hien_tai}")

# Thông tin người ở nằm cạnh giá phòng.
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    nguoi_o = st.text_input(
        "👤 Thông tin người ở",
        value=data["nguoi_o"],
        key=f"nguoi_o_{nam_chon}_{thang_chon}_{phong}",
        placeholder="Họ tên người thuê",
    )

with c2:
    gia_phong = st.number_input(
        "🏠 Giá phòng (VNĐ)",
        min_value=0,
        value=int(data["gia_phong"]),
        step=50000,
        key=f"gia_phong_{nam_chon}_{thang_chon}_{phong}",
    )

with c3:
    dien_cu = st.number_input(
        "⚡ Số điện CŨ",
        min_value=0,
        value=int(data["dien_cu"]),
        key=f"dien_cu_{nam_chon}_{thang_chon}_{phong}",
    )

with c4:
    dien_moi = st.number_input(
        "⚡ Số điện MỚI",
        min_value=0,
        value=int(data["dien_moi"]),
        key=f"dien_moi_{nam_chon}_{thang_chon}_{phong}",
    )

with c5:
    nuoc_cu = st.number_input(
        "💧 Số nước CŨ",
        min_value=0,
        value=int(data["nuoc_cu"]),
        key=f"nuoc_cu_{nam_chon}_{thang_chon}_{phong}",
    )

with c6:
    nuoc_moi = st.number_input(
        "💧 Số nước MỚI",
        min_value=0,
        value=int(data["nuoc_moi"]),
        key=f"nuoc_moi_{nam_chon}_{thang_chon}_{phong}",
    )

trang_thai = st.selectbox(
    "💳 Trạng thái thanh toán",
    TRANG_THAI,
    index=TRANG_THAI.index(data["trang_thai"]),
    key=f"trang_thai_{nam_chon}_{thang_chon}_{phong}",
)

if dien_moi < dien_cu:
    st.warning("Chỉ số điện mới nhỏ hơn số cũ. Tiền điện đang tính bằng 0.")

if nuoc_moi < nuoc_cu:
    st.warning("Chỉ số nước mới nhỏ hơn số cũ. Tiền nước đang tính bằng 0.")

data_cap_nhat = {
    "nam": int(nam_chon),
    "thang": int(thang_chon),
    "phong": int(phong),
    "nguoi_o": nguoi_o.strip(),
    "gia_phong": int(gia_phong),
    "dien_cu": int(dien_cu),
    "dien_moi": int(dien_moi),
    "nuoc_cu": int(nuoc_cu),
    "nuoc_moi": int(nuoc_moi),
    "trang_thai": trang_thai,
}

# Tính tiền xem trước theo dữ liệu đang nhập.
tien_xem_truoc = tinh_tien(
    data_cap_nhat, gia_dien, gia_nuoc, phi_khac
)

st.info(
    f"Tiền phòng: {dinh_dang_tien(gia_phong)}  |  "
    f"Tiền điện: {dinh_dang_tien(tien_xem_truoc['tien_dien'])}  |  "
    f"Tiền nước: {dinh_dang_tien(tien_xem_truoc['tien_nuoc'])}  |  "
    f"Tổng cộng: {dinh_dang_tien(tien_xem_truoc['tong_tien'])}"
)

if st.button("💾 LƯU THÔNG TIN PHÒNG", type="primary"):
    luu_phong(data_cap_nhat)

    # Đồng bộ số cũ vào tháng tiếp theo nếu tháng tiếp theo đã tồn tại.
    if thang_chon == 12:
        nam_sau, thang_sau = nam_chon + 1, 1
    else:
        nam_sau, thang_sau = nam_chon, thang_chon + 1

    data_thang_sau = doc_phong(nam_sau, thang_sau, phong)

    if data_thang_sau:
        data_thang_sau["dien_cu"] = int(dien_moi)
        data_thang_sau["nuoc_cu"] = int(nuoc_moi)
        luu_phong(data_thang_sau)

    st.success("Đã lưu thông tin phòng vào SQLite.")
    st.rerun()


# =====================================================
# BẢNG TỔNG HỢP THEO THÁNG
# =====================================================

st.divider()
st.header(f"📊 Bảng tổng hợp tiền trọ - {ky_hien_tai}")

ds_phong = doc_cac_phong(nam_chon, thang_chon, so_phong)

ket_qua = []

for d in ds_phong:
    tien = tinh_tien(d, gia_dien, gia_nuoc, phi_khac)

    ket_qua.append({
        "Phòng": f"Phòng {d['phong']}",
        "Người ở": d["nguoi_o"],
        "Giá phòng": d["gia_phong"],
        "Số điện cũ": d["dien_cu"],
        "Số điện mới": d["dien_moi"],
        "Tiền điện": tien["tien_dien"],
        "Số nước cũ": d["nuoc_cu"],
        "Số nước mới": d["nuoc_moi"],
        "Tiền nước": tien["tien_nuoc"],
        "Phí khác": phi_khac,
        "Tổng tiền": tien["tong_tien"],
        "Trạng thái": d["trang_thai"],
    })

if ket_qua:
    df = pd.DataFrame(ket_qua)

    tong_doanh_thu = int(df["Tổng tiền"].sum())
    da_thanh_toan = df[df["Trạng thái"] == "Đã thanh toán"]
    chua_thanh_toan = df[df["Trạng thái"] == "Chưa thanh toán"]

    tien_da_thu = int(da_thanh_toan["Tổng tiền"].sum())
    tien_chua_thu = int(chua_thanh_toan["Tổng tiền"].sum())

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("🏠 Số phòng", len(df))
    m2.metric("💰 Tổng tiền phải thu", dinh_dang_tien(tong_doanh_thu))
    m3.metric("✅ Đã thu", dinh_dang_tien(tien_da_thu))
    m4.metric("⏳ Chưa thu", dinh_dang_tien(tien_chua_thu))

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Giá phòng": st.column_config.NumberColumn(format="%d"),
            "Tiền điện": st.column_config.NumberColumn(format="%d"),
            "Tiền nước": st.column_config.NumberColumn(format="%d"),
            "Phí khác": st.column_config.NumberColumn(format="%d"),
            "Tổng tiền": st.column_config.NumberColumn(format="%d"),
        },
    )

    # Xuất CSV.
    csv_data = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label=f"📥 Xuất báo cáo {ky_hien_tai} (CSV)",
        data=csv_data,
        file_name=f"Bang_Tien_Phong_Thang_{thang_chon}_{nam_chon}.csv",
        mime="text/csv",
    )

    # Xuất PDF cho phòng đang chọn.
    st.subheader("🧾 Xuất phiếu thu PDF theo từng phòng")

    st.caption(
        "Phiếu PDF sử dụng dữ liệu đã lưu trong SQLite và đơn giá "
        "điện, nước, phí khác đang cấu hình ở thanh bên."
    )

    phong_pdf = st.selectbox(
        "Chọn phòng cần xuất phiếu PDF:",
        list(range(1, so_phong + 1)),
        format_func=lambda x: f"Phòng {x}",
        key=f"phong_pdf_{nam_chon}_{thang_chon}",
    )

    data_pdf = doc_phong(nam_chon, thang_chon, phong_pdf)

    if st.button("🔄 Tạo phiếu PDF"):
        if data_pdf:
            try:
                pdf_data = tao_pdf_phong(
                    data_pdf, gia_dien, gia_nuoc, phi_khac
                )
                st.session_state[
                    f"pdf_{nam_chon}_{thang_chon}_{phong_pdf}"
                ] = pdf_data
                st.success("Đã tạo phiếu PDF.")
            except (FileNotFoundError, OSError) as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Không tạo được PDF: {exc}")

    pdf_key = f"pdf_{nam_chon}_{thang_chon}_{phong_pdf}"

    if pdf_key in st.session_state:
        st.download_button(
            label=f"📄 Tải phiếu thu Phòng {phong_pdf} (PDF)",
            data=st.session_state[pdf_key],
            file_name=(
                f"Phieu_Thu_Phong_{phong_pdf}_"
                f"Thang_{thang_chon}_{nam_chon}.pdf"
            ),
            mime="application/pdf",
            key=f"tai_pdf_{nam_chon}_{thang_chon}_{phong_pdf}",
        )

else:
    st.info("Chưa có dữ liệu phòng cho kỳ này.")

st.divider()
st.caption(
    f"🗄️ Database SQLite: {DB_PATH.name} | "
    "Dữ liệu được lưu trên máy chạy ứng dụng."
)
