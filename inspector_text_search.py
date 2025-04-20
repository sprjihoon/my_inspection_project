import streamlit as st
import os, uuid
from PIL import Image
from common import get_connection, now_str

# ───────── DB & 폴더 준비 ─────────
con = get_connection()
cur = con.cursor()
IMG_DIR = "product_images"
os.makedirs(IMG_DIR, exist_ok=True)

# ───────── helper ─────────

def save_image(file):
    """업로드 이미지를 디스크에 저장하고 파일명을 반환"""
    ext = file.name.split(".")[-1]
    fname = f"{uuid.uuid4()}.{ext}"
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(file.getbuffer())
    return fname

def ensure_img_table():
    cur.execute(
        """CREATE TABLE IF NOT EXISTS product_images(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INT,
            file_name   TEXT,
            is_main     INT,
            uploaded_at TEXT)"""
    )

HR = "<hr style='margin:0.4rem 0;border:0;border-top:1px dashed #ccc;'>"

# ───────── main ─────────

def main():
    st.title("검수자 – 텍스트 검색 ▸ 상품·SKU 등록 & 검수")

    # 권한 확인
    if st.session_state.get("user_role") != "inspector":
        st.warning("접근 권한이 없습니다. (검수자 전용)")
        st.stop()

    # 직전 저장 알림
    if "save_msg" in st.session_state:
        st.success(st.session_state.pop("save_msg"))

        # ── 저장 후 검색창 리셋 플래그 처리 ──
    if st.session_state.pop("reset_search", False):
        # 위젯 생성 전에 값을 미리 비워 두어야 예외가 발생하지 않음
        st.session_state["search_q"] = ""

    # ① 검색 -------------------------------------------------- --------------------------------------------------
    q = st.text_input("🔍 검색어 (제품명·바코드)", key="search_q")
    pid = st.session_state.get("pid")

    if q:
        rows = cur.execute(
            "SELECT p.id, p.product_name, GROUP_CONCAT(s.barcode) "
            "FROM products p LEFT JOIN skus s ON s.product_id = p.id "
            "WHERE p.product_name LIKE ? OR s.barcode LIKE ? "
            "GROUP BY p.id LIMIT 30",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        if rows:
            mapping = {f"{r[1]} (바코드:{(r[2] or '').split(',')[0]})": r[0] for r in rows}
            sel = st.selectbox("검색 결과", list(mapping.keys()))
            pid = mapping[sel]
            st.session_state["pid"] = pid
        else:
            st.info("검색 결과 없음 — 신규 상품으로 계속 진행합니다.")
            st.session_state.pop("pid", None)
            pid = None

    # ② 상품 기본 정보 ---------------------------------------
    st.markdown("---")
    st.subheader("📦 상품 정보")
    if pid:
        pname_d, vendor_d, oper_d, loc_d = cur.execute(
            "SELECT product_name,vendor_id,operator_id,location FROM products WHERE id=?",
            (pid,),
        ).fetchone()
    else:
        pname_d = vendor_d = oper_d = loc_d = ""

    pname    = st.text_input("제품명", pname_d, disabled=bool(pid))
    vendor   = st.text_input("도매처", vendor_d or "")
    oper     = st.text_input("브랜드/운영자", oper_d or "", disabled=bool(pid))
    location = st.text_input("로케이션", loc_d or "")

    # ③ SKU 입력 / 검수 -------------------------------------
    sku_records = []  # (c,s,bc,n,d,p,comment)
    if not pid:
        st.markdown("#### 신규 SKU 생성 & 1차 검수 수량 입력")
        cols_head = st.columns(4)
        colors_in = cols_head[0].text_input("색상들(쉼표)")
        sizes_in  = cols_head[1].text_input("사이즈들(쉼표)")
        def_n     = cols_head[2].number_input("공통 정상", 0, step=1)
        def_d     = cols_head[3].number_input("공통 불량", 0, step=1)
        colors = [c.strip() for c in colors_in.split(",") if c.strip()] or [""]
        sizes  = [s.strip() for s in sizes_in.split(",") if s.strip()] or [""]
        for idx, (c, s) in enumerate([(c, s) for c in colors for s in sizes], 1):
            st.markdown(f"**SKU {idx} — {c or '-'} / {s or '-'}**")
            bc = st.text_input("바코드", key=f"bc_{idx}")
            nc, dc, pc = st.columns(3)
            n = nc.number_input("정상", 0, key=f"n_{idx}", value=def_n)
            d = dc.number_input("불량", 0, key=f"d_{idx}", value=def_d)
            p = pc.number_input("보류", 0, key=f"p_{idx}")
            cm = st.text_input("보류 코멘트", key=f"cmt_{idx}") if p else ""
            sku_records.append((c, s, bc, n, d, p, cm))
            st.markdown(HR, unsafe_allow_html=True)
    else:
        st.markdown("#### 기존 SKU 1차 검수 수량 입력")
        for idx, (c, s, bc) in enumerate(
            cur.execute("SELECT color,size,barcode FROM skus WHERE product_id=? GROUP BY barcode", (pid,)), 1):
            st.markdown(f"**{idx}. {c or '-'} / {s or '-'} — 바코드:{bc}**")
            nc, dc, pc = st.columns(3)
            n = nc.number_input("정상", 0, key=f"n_{bc}")
            d = dc.number_input("불량", 0, key=f"d_{bc}")
            p = pc.number_input("보류", 0, key=f"p_{bc}")
            cm = st.text_input("보류 코멘트", key=f"cmt_{bc}") if p else ""
            sku_records.append((c, s, bc, n, d, p, cm))
            st.markdown(HR, unsafe_allow_html=True)

    # ④ 이미지 업로드 ----------------------------------------
    st.markdown("#### 이미지 업로드 (최대 5장)")
    files = st.file_uploader("이미지", ["jpg", "jpeg", "png"], accept_multiple_files=True, key="img_up")
    if files and len(files) > 5:
        st.warning("5장까지만 업로드됩니다.")
        files = files[:5]
    if files:
        st.image([Image.open(f) for f in files], width=120)

    # ⑤ 저장 --------------------------------------------------
    if st.button("✅ 저장"):
        if not pname.strip():
            st.error("제품명을 입력하세요"); st.stop()

        # products 테이블 (신규일 때)
        if not pid:
            cur.execute(
                "INSERT INTO products(product_name,vendor_id,operator_id,location,created_at) "
                "VALUES(?,?,?,?,?)",
                (pname, vendor, oper, location, now_str()),
            )
            pid = cur.lastrowid

        # SKU & inspection_results
        inserted = 0
        for c, s, bc, n, d, p, cm in sku_records:
            if not bc:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO skus(product_id,barcode,vendor,status,created_at,color,size) "
                "VALUES(?,?,?,?,?,?,?)",
                (pid, bc, vendor, "정상", now_str(), c, s),
            )
            total = n + d + p
            if total:
                status = "보류" if p else "불량" if d else "정상"
                cur.execute(
                    "INSERT INTO inspection_results("\
                    "image_name,product_id,barcode,operator,similarity_pct,"\
                    "normal_qty,defect_qty,pending_qty,total_qty,comment,inspected_at,status) "\
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("", pid, bc, oper, None, int(n), int(d), int(p), int(total), cm, now_str(), status),
                )
                inserted += 1

        # 이미지 저장
        ensure_img_table()
        for f in files or []:
            fname = save_image(f)
            cur.execute(
                "INSERT INTO product_images(product_id,file_name,is_main,uploaded_at) VALUES(?,?,0,?)",
                (pid, fname, now_str()),
            )

        con.commit()

        # UI 초기화 & 메시지
        for k in ("pid", "img_up"):
            st.session_state.pop(k, None)
        st.session_state["reset_search"] = True
        st.session_state["save_msg"] = f"검수 레코드 {inserted}건 저장 완료!"
        st.rerun()

if __name__ == "__main__":
    main()
