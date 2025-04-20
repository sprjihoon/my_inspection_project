################################################################################
# vendor_product_list.py  –  제품 목록 / 이미지·정보 관리 (inspector·operator)
################################################################################
import streamlit as st, os, uuid, math
from PIL import Image
from common import get_connection, now_str

# ══════════════════════════════════════════════════════════════════════════════
#  환경 설정 & 연결
# ══════════════════════════════════════════════════════════════════════════════
BASE_DIR   = os.getcwd()
IMG_DIR_DB = os.path.join(BASE_DIR, "db_images")     # 모든 이미지 저장·조회
os.makedirs(IMG_DIR_DB, exist_ok=True)

con = get_connection()
cur = con.cursor()

# ══════════════════════════════════════════════════════════════════════════════
#  경로 해석: 절대 → db_images
# ══════════════════════════════════════════════════════════════════════════════
def resolve_path(p: str | None):
    """DB에 저장된 경로/파일명을 실제 파일 경로로 변환."""
    if not p:
        return None
    if os.path.exists(p):                       # 절대/상대 그대로
        return p
    cand = os.path.join(IMG_DIR_DB, os.path.basename(p))
    return cand if os.path.exists(cand) else None

# ══════════════════════════════════════════════════════════════════════════════
#  권한 체크
# ══════════════════════════════════════════════════════════════════════════════
role = st.session_state.get("user_role", "")
if role not in ("operator", "inspector"):
    st.warning("접근 권한이 없습니다. (운영자·검수자)"); st.stop()

st.title("📦 상품 목록 / 이미지·정보 관리")
st.caption(f"role = {role}")

# ══════════════════════════════════════════════════════════════════════════════
#  필터 영역
# ══════════════════════════════════════════════════════════════════════════════
if role == "operator":
    my_brand = cur.execute(
        "SELECT operator_id FROM users WHERE id=?",
        (st.session_state["user_id"],)
    ).fetchone()
    if not my_brand or not my_brand[0]:
        st.error("계정에 operator_id(브랜드)가 지정되지 않았습니다."); st.stop()
    id_col, sel_id = "operator_id", my_brand[0]
    st.info(f"현재 브랜드: **{sel_id}** (읽기 전용)")
else:  # inspector
    mode = st.radio("분류 기준", ["도매처별", "브랜드별"], horizontal=True)
    if mode == "도매처별":
        id_col, label = "vendor_id", "도매처"
        ids = [r[0] for r in cur.execute(
            "SELECT DISTINCT vendor_id FROM products WHERE vendor_id IS NOT NULL ORDER BY 1")]
    else:
        id_col, label = "operator_id", "브랜드"
        ids = [r[0] for r in cur.execute(
            "SELECT DISTINCT operator_id FROM products WHERE operator_id IS NOT NULL ORDER BY 1")]
    sel_id = st.selectbox(f"{label} 선택", ["전체"] + ids)

col_kw, col_pp, col_view = st.columns([4, 1, 2])
kw        = col_kw.text_input("🔍 검색 (제품명 / 옵션 / 바코드 / 로케이션 / ID)")
per_page  = col_pp.selectbox("표시수", [30, 50, 100], index=0)
view_mode = col_view.radio("보기 방식", ["갤러리", "리스트"], horizontal=True, index=1)

# ══════════════════════════════════════════════════════════════════════════════
#  데이터 로드 (products + 옵션/바코드 + 썸네일 1장)
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def load_products(filter_col, filter_val, keyword):
    where, params = [], []
    if role == "operator" or filter_val != "전체":
        where.append(f"p.{filter_col}=?"); params.append(filter_val)
    if keyword:
        like = f"%{keyword}%"
        where.append("("
                     "p.product_name LIKE ? OR "
                     "s.option_text LIKE ? OR "
                     "s.barcode_text LIKE ? OR "
                     "p.location LIKE ? OR "
                     "CAST(p.id AS TEXT) LIKE ?)")
        params += [like]*5
    wsql = "WHERE " + " AND ".join(where) if where else ""

    sql = f"""
    SELECT p.id,
           p.product_name,
           IFNULL(s.option_text,'-')   AS option_text,
           IFNULL(s.barcode_text,'-')  AS barcode_text,
           p.location,
           (SELECT COALESCE(image_path, file_name)
              FROM product_images
             WHERE product_id = p.id
             ORDER BY is_main DESC, id ASC
             LIMIT 1)                  AS thumb,
           p.created_at
      FROM products p
      LEFT JOIN (
            SELECT product_id,
                   GROUP_CONCAT(DISTINCT color||'/'||size) AS option_text,
                   GROUP_CONCAT(DISTINCT barcode)          AS barcode_text
              FROM skus
             GROUP BY product_id
      ) s ON s.product_id = p.id
      {wsql}
      ORDER BY p.created_at DESC;
    """
    return cur.execute(sql, params).fetchall()

rows = load_products(id_col, sel_id, kw)

# ══════════════════════════════════════════════════════════════════════════════
#  페이지 나누기
# ══════════════════════════════════════════════════════════════════════════════
page_cnt = max(1, math.ceil(len(rows)/per_page))
page_num = st.number_input("페이지", 1, page_cnt, 1, key="page_num")
view = rows[(page_num-1)*per_page : page_num*per_page]

# ══════════════════════════════════════════════════════════════════════════════
#  목록 표시 (갤러리 / 리스트)
# ══════════════════════════════════════════════════════════════════════════════
sel_key = "sel_pid"
sel_pid = st.session_state.get(sel_key)
delete_ids = []

if view_mode == "갤러리":
    GRID = 4
    for r in range(math.ceil(len(view)/GRID)):
        cols = st.columns(GRID)
        for i in range(GRID):
            idx = r*GRID + i
            if idx >= len(view):
                cols[i].empty(); continue
            pid, pname, opt, bar, loc, thumb, _ = view[idx]
            with cols[i]:
                ch_key = f"chk_{pid}_{idx}"
                if st.checkbox("", key=ch_key):
                    delete_ids.append(pid)

                ipath = resolve_path(thumb)
                if ipath:
                    st.image(ipath, width=130)
                else:
                    st.markdown(
                        "<div style='width:130px;height:130px;border:1px dashed #bbb;"
                        "display:flex;align-items:center;justify-content:center;font-size:11px'>No<br>Image</div>",
                        unsafe_allow_html=True)

                st.markdown(f"**{pname}**")
                st.caption(f"{opt} ｜ {bar}")
                st.caption(f"ID:{pid} ｜ {loc or '-'}")
                if st.button("상세", key=f"card_{pid}"):
                    st.session_state[sel_key] = pid
                    sel_pid = pid
else:  # 리스트
    import pandas as pd
    df = pd.DataFrame(view, columns=["ID", "제품명", "옵션", "바코드", "로케이션", "thumb", "created"])
    st.dataframe(df[["ID", "제품명", "옵션", "바코드", "로케이션"]],
                 use_container_width=True, height=600)
    manual = st.number_input("상세 ID 입력", 0, step=1, key="manual_sel")
    if manual and cur.execute("SELECT 1 FROM products WHERE id=?", (manual,)).fetchone():
        st.session_state[sel_key] = int(manual)
        sel_pid = int(manual)

# ══════════════════════════════════════════════════════════════════════════════
#  일괄 삭제
# ══════════════════════════════════════════════════════════════════════════════
if delete_ids and role == "inspector":
    if st.button(f"🗑️ 선택된 {len(delete_ids)}개 삭제"):
        qmarks = ",".join("?"*len(delete_ids))
        cur.execute(f"DELETE FROM products        WHERE id IN ({qmarks})", delete_ids)
        cur.execute(f"DELETE FROM product_images WHERE product_id IN ({qmarks})", delete_ids)
        cur.execute(f"DELETE FROM skus           WHERE product_id IN ({qmarks})", delete_ids)
        con.commit(); st.success("삭제 완료"); st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  상세 페이지
# ══════════════════════════════════════════════════════════════════════════════
if sel_pid:
    st.divider(); st.success(f"선택 상품 ID: {sel_pid}")

    # -- 이미지 리스트 ---------------------------------------------------------
    imgs = cur.execute(
        "SELECT id, COALESCE(image_path,file_name) AS img, is_main "
        "FROM product_images WHERE product_id=? ORDER BY id", (sel_pid,)
    ).fetchall()

    st.subheader("📷 이미지 관리")
    for iid, fn, is_main in imgs:
        c1, c2, c3 = st.columns([3, 1, 1])
        ipath = resolve_path(fn)
        if ipath:
            c1.image(ipath, width=120)
        else:
            c1.markdown(
                "<div style='width:120px;height:120px;border:1px dashed #bbb;"
                "display:flex;align-items:center;justify-content:center;font-size:10px;'>No Img</div>",
                unsafe_allow_html=True)

        if role == "inspector":
            if c2.radio("메인", ["", "★"], index=(1 if is_main else 0), key=f"star_{iid}") == "★":
                cur.execute("UPDATE product_images SET is_main=0 WHERE product_id=?", (sel_pid,))
                cur.execute("UPDATE product_images SET is_main=1 WHERE id=?", (iid,))
                con.commit(); st.rerun()
            if c3.button("삭제", key=f"delimg_{iid}"):
                cur.execute("DELETE FROM product_images WHERE id=?", (iid,))
                con.commit(); st.rerun()

    # -- 새 이미지 업로드 ------------------------------------------------------
    if role == "inspector":
        up = st.file_uploader("새 이미지 추가", ["jpg", "jpeg", "png"], accept_multiple_files=True)
        if up:
            for f in up:
                fname = f"{uuid.uuid4()}.jpg"
                save_path = os.path.join(IMG_DIR_DB, fname)
                Image.open(f).convert("RGB").save(save_path, quality=90)
                cur.execute(
                    "INSERT INTO product_images(product_id,image_path,is_main,uploaded_at)"
                    "VALUES(?,?,0,?)", (sel_pid, fname, now_str()))
            con.commit(); st.rerun()

    # -- 제품 정보 -------------------------------------------------------------
    if role == "inspector":
        st.subheader("✏️ 제품 정보")
        p = cur.execute(
            "SELECT product_name, vendor_id, operator_id, location "
            "FROM products WHERE id=?", (sel_pid,)
        ).fetchone()
        if p:
            pn = st.text_input("제품명",  p[0])
            vd = st.text_input("도매처",  p[1] or "")
            op = st.text_input("브랜드",  p[2] or "")
            lc = st.text_input("로케이션", p[3] or "")
            if st.button("💾 저장"):
                cur.execute(
                    "UPDATE products SET product_name=?, vendor_id=?, operator_id=?, location=? "
                    "WHERE id=?",
                    (pn, vd or None, op or None, lc or None, sel_pid)
                )
                con.commit(); st.success("수정 완료"); st.rerun()
            if st.button("🗑️ 제품 삭제"):
                cur.execute("DELETE FROM products        WHERE id=?", (sel_pid,))
                cur.execute("DELETE FROM product_images WHERE product_id=?", (sel_pid,))
                cur.execute("DELETE FROM skus           WHERE product_id=?", (sel_pid,))
                con.commit(); st.success("삭제 완료")
                st.session_state.pop(sel_key, None); st.rerun()
