import streamlit as st
import os, uuid
from PIL import Image
from common import get_connection, now_str

con = get_connection()
cur = con.cursor()

IMG_DIR = "product_images"
os.makedirs(IMG_DIR, exist_ok=True)

# ───────────────── helper ─────────────────

def save_image(file):
    ext = file.name.split(".")[-1]
    fname = f"{uuid.uuid4()}.{ext}"
    with open(os.path.join(IMG_DIR, fname), "wb") as f:
        f.write(file.getbuffer())
    return fname

def ensure_tables():
    cur.execute(
        """CREATE TABLE IF NOT EXISTS product_images(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 product_id INT,
                 file_name TEXT,
                 is_main INT,
                 uploaded_at TEXT)"""
    )

# ───────────────── main ─────────────────

def main():
    st.title("검수자 – 텍스트 검색 ▸ 신규 상품 등록 ▸ 검수")
    if st.session_state.get("user_role") != "inspector":
        st.warning("접근 권한이 없습니다. (검수자 전용)")
        st.stop()

    # 1️⃣ 검색
    q = st.text_input("🔍 검색어 (제품명·바코드)")
    pid = None
    if q:
        rows = cur.execute(
            "SELECT p.id, p.product_name, GROUP_CONCAT(s.barcode) FROM products p LEFT JOIN skus s ON s.product_id=p.id WHERE p.product_name LIKE ? OR s.barcode LIKE ? GROUP BY p.id LIMIT 30",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        if rows:
            mapping = {f"{r[1]} (바코드:{(r[2] or '').split(',')[0]})": r[0] for r in rows}
            pid = mapping[st.selectbox("검색 결과", list(mapping.keys()))]
        else:
            st.info("검색 결과 없음 — 신규 상품 등록 모드")

    # 2️⃣ 상품 정보
    st.markdown("---")
    st.subheader("📦 상품 정보")
    if pid:
        pname_d, vendor_d, oper_d, loc_d = cur.execute(
            "SELECT product_name, vendor_id, operator_id, location FROM products WHERE id=?", (pid,)
        ).fetchone()
    else:
        pname_d = vendor_d = oper_d = loc_d = ""

    pname  = st.text_input("제품명", pname_d, disabled=bool(pid))
    vendor = st.text_input("도매처", vendor_d or "")
    oper   = st.text_input("브랜드/운영자", oper_d or "", disabled=bool(pid))
    location = st.text_input("로케이션", loc_d or "")

    # ── 신규 상품용 옵션/바코드 입력
    bc_inputs = {}
    if not pid:
        st.markdown("#### SKU 옵션 & 바코드")
        colors_in = st.text_input("색상 목록 (쉼표 구분)")
        sizes_in  = st.text_input("사이즈 목록 (쉼표 구분)")
        colors = [c.strip() for c in colors_in.split(",") if c.strip()] or [""]
        sizes  = [s.strip() for s in sizes_in.split(",") if s.strip()] or [""]
        combos = [(c, s) for c in colors for s in sizes]
        for c, s in combos:
            label = f"{c or '-'} / {s or '-'} 바코드"
            bc_inputs[(c, s)] = st.text_input(label)

    # 이미지 업로드
    st.markdown("#### 이미지 업로드 (최대 5장)")
    files = st.file_uploader("이미지 파일", ["jpg","jpeg","png"], accept_multiple_files=True)
    if files and len(files) > 5:
        st.warning("5장까지만 업로드됩니다.")
        files = files[:5]
    if files:
        st.image([Image.open(f) for f in files], width=120)

    # 3️⃣ 검수 수량
    st.markdown("---")
    st.subheader("📋 검수 수량")
    c1,c2,c3 = st.columns(3)
    nqty = c1.number_input("정상",0,step=1)
    dqty = c2.number_input("불량",0,step=1)
    pqty = c3.number_input("보류",0,step=1)
    total = nqty+dqty+pqty
    st.info(f"총 수량: {total}")
    comment = st.text_area("보류 사유 / 코멘트", disabled=(pqty==0))

    if st.button("✅ 저장"):
        if not pname.strip():
            st.error("제품명을 입력하세요"); st.stop()
        if total==0:
            st.error("수량이 0입니다"); st.stop()

        # 신규 상품 DB
        if not pid:
            cur.execute(
                "INSERT INTO products(product_name,vendor_id,operator_id,location,created_at) VALUES(?,?,?,?,?)",
                (pname,None,None,location,now_str()),
            )
            pid = cur.lastrowid
            # SKU + 바코드
            for (c,s), bc in bc_inputs.items():
                cur.execute(
                    "INSERT INTO skus(product_id,barcode,vendor,status,created_at,color,size) VALUES(?,?,?,?,?,?,?)",
                    (pid, bc, vendor, "정상", now_str(), c, s),
                )
        else:
            # 기존 상품이면 기본 SKU 보존
            pass

        # 이미지 저장
        ensure_tables()
        for f in files or []:
            fname = save_image(f)
            cur.execute("INSERT INTO product_images(product_id,file_name,is_main,uploaded_at) VALUES(?,?,0,?)", (pid,fname,now_str()))

        # 검수 결과
        status = "보류" if pqty else "불량" if dqty else "정상"
        cur.execute(
            "INSERT INTO inspection_results(product_id,operator,normal_qty,defect_qty,pending_qty,total_qty,comment,inspected_at,status) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid,oper,int(nqty),int(dqty),int(pqty),int(total),comment,now_str(),status),
        )
        con.commit()
        st.success("저장 완료!")
        st.rerun()

if __name__ == "__main__":
    main()
