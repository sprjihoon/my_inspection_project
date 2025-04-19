import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from barcode import Code128
from barcode.writer import ImageWriter
import io
from common import get_connection

con = get_connection()

# 라벨 생성 함수
def generate_label_image(product_name, option, barcode_text, location, label_type="정상", width=400, height=200):
    barcode = Code128(barcode_text, writer=ImageWriter())
    barcode_buffer = io.BytesIO()
    barcode.write(barcode_buffer)
    barcode_buffer.seek(0)
    barcode_img = Image.open(barcode_buffer).convert("RGB").resize((width - 20, 80))

    label = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(label)
    font = ImageFont.load_default()

    y_offset = 10
    label_title = f"[{label_type}] 제품명: {product_name}" if label_type != "정상" else f"제품명: {product_name}"
    draw.text((10, y_offset), label_title, fill="black", font=font)
    draw.text((10, y_offset + 20), f"옵션: {option}", fill="black", font=font)
    draw.text((10, y_offset + 40), f"로케이션: {location}", fill="black", font=font)
    label.paste(barcode_img, (10, y_offset + 70))

    return label

def main():
    st.title("검수자 – 검수 결과 리스트")

    role = st.session_state.get("user_role", "")
    if role != "inspector":
        st.warning("접근 권한이 없습니다. (검수자 전용)")
        st.stop()

    df = pd.read_sql("""
        SELECT ir.id, ir.inspected_at, ir.status,
               p.product_name, p.location,
               ir.barcode,
               ir.operator, ir.normal_qty, ir.defect_qty,
               ir.pending_qty, ir.total_qty,
               ir.similarity_pct, ir.comment
          FROM inspection_results ir
          JOIN products p ON ir.product_id = p.id
      ORDER BY ir.inspected_at DESC
    """, con)

    df["similarity_pct"] = df["similarity_pct"].apply(
        lambda v: "검색등록" if pd.isna(v) else f"{v:.1f}%")

    ops = ["전체"] + sorted(df["operator"].dropna().unique())
    sts = ["전체"] + sorted(df["status"].unique())
    op_f = st.selectbox("브랜드", ops)
    st_f = st.selectbox("상태", sts)
    if op_f != "전체":
        df = df[df["operator"] == op_f]
    if st_f != "전체":
        df = df[df["status"] == st_f]

    selected = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    if st.button("💾 수정 저장") and not selected.empty:
        for _, row in selected.iterrows():
            con.execute("""
                UPDATE inspection_results
                   SET comment=?, status=?
                 WHERE id=? """,
                 (row["comment"], row["status"], int(row["id"])))
        con.commit()
        st.success("수정 저장 완료")
        st.rerun()

    if st.button("🗑️ 선택 행 삭제") and not selected.empty:
        ids = tuple(selected["id"].tolist())
        con.execute(
            f"DELETE FROM inspection_results WHERE id IN ({','.join('?'*len(ids))})",
            ids)
        con.commit()
        st.success("삭제 완료")
        st.rerun()

    # 라벨 출력
    if not selected.empty:
        st.subheader("🖨️ 선택 행 바코드 라벨 출력")
        row = selected.iloc[0]

        # 옵션 가져오기
        sku_info = con.execute("SELECT color, size FROM skus WHERE barcode=?", (row["barcode"],)).fetchone()
        color, size = sku_info if sku_info else ("", "")
        option_text = f"{color} / {size}" if color or size else "-"

        width = st.slider("라벨 너비(px)", 300, 800, 400)
        height = st.slider("라벨 높이(px)", 150, 400, 200)

        for label_type, qty in zip(["정상", "불량", "보류"], [row['normal_qty'], row['defect_qty'], row['pending_qty']]):
            if qty > 0:
                st.markdown(f"#### ▶️ {label_type} 수량: {qty} (출력 라벨 미리보기)")
                for i in range(int(qty)):
                    label_img = generate_label_image(
                        product_name=row['product_name'],
                        option=option_text,
                        barcode_text=row['barcode'],
                        location=row['location'],
                        label_type=label_type,
                        width=width,
                        height=height
                    )
                    st.image(label_img, caption=f"{label_type} 라벨 {i+1}", use_column_width=False)

                    img_buffer = io.BytesIO()
                    label_img.save(img_buffer, format="PNG")
                    st.download_button(
                        f"📥 {label_type} 라벨 {i+1} 다운로드",
                        img_buffer.getvalue(),
                        file_name=f"{label_type}_label_{i+1}.png"
                    )

if __name__ == "__main__":
    main()
