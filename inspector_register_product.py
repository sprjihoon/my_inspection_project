import streamlit as st
import os
import sqlite3
from PIL import Image
from common import get_connection, now_str, log_activity

def save_image_file(uploaded_file, folder="db_images"):
    os.makedirs(folder, exist_ok=True)
    filename = f"{now_str().replace(':', '').replace(' ', '_')}_{uploaded_file.name}"
    filepath = os.path.join(folder, filename)
    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return filename

def main():
    st.title("검수자 – 상품 등록")

    role = st.session_state.get("user_role", "")
    if role != "inspector":
        st.warning("접근 권한이 없습니다. (검수자 전용)")
        st.stop()

    con = get_connection()
    cur = con.cursor()

    # 이미지 업로드 및 기준 이미지 선택
    st.subheader("제품 이미지 업로드")
    uploaded_files = st.file_uploader("최대 5장 업로드", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

    if uploaded_files:
        if len(uploaded_files) > 5:
            st.warning("5장까지만 업로드됩니다.")
            uploaded_files = uploaded_files[:5]

        st.subheader("기준 이미지 선택")
        selected_main_idx = st.radio(
            "기준 이미지로 사용할 파일을 선택하세요.",
            options=range(len(uploaded_files)),
            format_func=lambda i: uploaded_files[i].name,
            horizontal=True
        )

        cols = st.columns(len(uploaded_files))
        for i, (col, file) in enumerate(zip(cols, uploaded_files)):
            with col:
                st.image(file, use_container_width=True)
                if i == selected_main_idx:
                    st.markdown("✅ 기준 이미지", unsafe_allow_html=True)

    # 상품 정보 입력
    st.subheader("기본 정보 입력")
    pname = st.text_input("제품명")
    oper = st.text_input("브랜드명 (운영자)")
    vendor = st.text_input("도매처")
    location = st.text_input("보관 위치 (예: A-3-2)")

    # 옵션 입력
    st.subheader("옵션(SKU) 입력")
    colors_in = st.text_input("색상들 (예: Red, Blue)")
    sizes_in = st.text_input("사이즈들 (예: S, M)")
    colors = [c.strip() for c in colors_in.split(",") if c.strip()]
    sizes = [s.strip() for s in sizes_in.split(",") if s.strip()]
    combos = [(c, s) for c in colors for s in sizes]

    # 바코드 입력
    bc_inputs = {}
    if combos:
        st.subheader("조합별 바코드 입력")
        for c, s in combos:
            bc_inputs[(c, s)] = st.text_input(f"바코드 - {c}/{s}")

    if st.button("상품 등록"):
        if not (pname and uploaded_files):
            st.error("제품명과 이미지 업로드는 필수입니다.")
            st.stop()

        main_image_file = uploaded_files[selected_main_idx]
        main_image_path = save_image_file(main_image_file)

        # products 테이블에 저장
        cur.execute("""
            INSERT INTO products(product_name, vendor_id, operator_id, main_image, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pname, vendor, oper, main_image_path, location, now_str()))
        product_id = cur.lastrowid

        for i, file in enumerate(uploaded_files):
            saved_name = save_image_file(file)
            is_main = 1 if i == selected_main_idx else 0
            cur.execute("""
                INSERT INTO product_images(product_id, image_path, is_main, uploaded_at)
                VALUES (?, ?, ?, ?)
            """, (product_id, saved_name, is_main, now_str()))

        for (color, size), barcode in bc_inputs.items():
            if not barcode.strip():
                continue
            cur.execute("""
                INSERT INTO skus(product_id, barcode, vendor, status, created_at, color, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (product_id, barcode, vendor, "정상", now_str(), color, size))

        con.commit()
        st.success(f"상품 등록 완료! (ID: {product_id})")

        log_activity(
            user_id=st.session_state["user_id"],
            action_type="CREATE",
            table_name="products",
            record_id=product_id,
            old_data="{}",
            new_data=f'{{"product_name": "{pname}"}}'
        )

if __name__ == "__main__":
    main()
