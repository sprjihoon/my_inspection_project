import streamlit as st
import uuid, os, math, hashlib
from PIL import Image
from common import get_connection, now_str

"""
Spring Fulfillment – 상품 목록/이미지 관리 v7  (2025‑04‑21)
────────────────────────────────────────
🆕 변경 요약
────────────────────
* **폴더를 하나로 통일** → `db_images/`만 사용
  · 과거·현재 모든 이미지가 여기에 있으며, 새 업로드도 동일 폴더에 저장
* `images/` 폴더는 더 이상 사용하지 않음 (경로 탐색에서 보조용으로만 유지)
"""

## ─────────────────────────────────────
#   설정 / DB 연결
## ─────────────────────────────────────
BASE_DIR    = os.getcwd()
IMG_DIR     = os.path.join(BASE_DIR, "db_images")   # 이미지 전용 폴더 (과거+신규)
LEGACY_DIR  = os.path.join(BASE_DIR, "images")      # 옛 버그로 생성됐던 폴더 (읽기만)

os.makedirs(IMG_DIR, exist_ok=True)          # 주 폴더
if os.path.isdir(LEGACY_DIR):                # 존재할 때만 읽기 폴더로 사용
    pass

con = get_connection(); cur = con.cursor()

## ─────────────────────────────────────
#   유틸: 이미지 경로 해석
## ─────────────────────────────────────

def resolve_path(p: str | None) -> str | None:
    """절대·상대·db_images/·images/ 순으로 실제 경로 반환"""
    if not p:
        return None
    # 1) 절대·현재경로 그대로 존재할 때
    if os.path.exists(p):
        return p
    # 2) db_images/ 폴더
    cand = os.path.join(IMG_DIR, os.path.basename(p))
    if os.path.exists(cand):
        return cand
    # 3) images/ (legacy)
    if os.path.isdir(LEGACY_DIR):
        cand = os.path.join(LEGACY_DIR, os.path.basename(p))
        if os.path.exists(cand):
            return cand
    return None

## ─────────────────────────────────────
#   권한 체크
## ─────────────────────────────────────
role = st.session_state.get("user_role", "")
if role not in ("operator", "inspector"):
    st.warning("접근 권한이 없습니다. (운영자·검수자)")
    st.stop()

st.title("📦 상품 목록 / 이미지 관리")

## ─────────────────────────────────────
#   필터 영역
## ─────────────────────────────────────
if role == "operator":
    my_brand_row = cur.execute("SELECT operator_id FROM users WHERE id=?", (st.session_state.get("user_id"),)).fetchone()
    if not my_brand_row or not my_brand_row[0]:
        st.error("계정에 operator_id(브랜드)가 지정되지 않았습니다.")
        st.stop()
    id_col, sel_id = "operator_id", my_brand_row[0]
    st.info(f"현재 브랜드: **{sel_id}** (읽기 전용)")
else:
    mode = st.radio("분류 기준", ["도매처별", "브랜드별"], horizontal=True)
    if mode == "도매처별":
        id_col, label = "vendor_id", "도매처"
        ids = [r[0] for r in cur.execute("SELECT DISTINCT vendor_id FROM products WHERE vendor_id IS NOT NULL ORDER BY 1")]
    else:
        id_col, label = "operator_id", "브랜드"
        ids = [r[0] for r in cur.execute("SELECT DISTINCT operator_id FROM products WHERE operator_id IS NOT NULL ORDER BY 1")]
    sel_id = st.selectbox(f"{label} 선택", ["전체"] + ids)

col_kw, col_n = st.columns([3, 1])
kw       = col_kw.text_input("🔍 제품명 / ID / 로케이션", key="prod_kw")
per_page = col_n.selectbox("표시수", [30, 50, 100], 0)

## ─────────────────────────────────────
#   데이터 로드 (캐시)
## ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_products(id_col: str, sel_id: str | int | None, kw: str | None):
    where, params = [], []
    if sel_id and sel_id != "전체":
        where.append(f"p.{id_col}=?")
        params.append(sel_id)
    if kw:
        like = f"%{kw}%"
        where.append("(p.product_name LIKE ? OR p.location LIKE ? OR CAST(p.id AS TEXT) LIKE ?)")
        params += [like] * 3
    wsql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT p.id, p.product_name, p.location,
               COALESCE(
                   (SELECT COALESCE(image_path, file_name) FROM product_images WHERE product_id=p.id AND is_main=1 LIMIT 1),
                   (SELECT COALESCE(image_path, file_name) FROM product_images WHERE product_id=p.id LIMIT 1)
               ) AS thumb,
               p.created_at
          FROM products p
          {wsql}
         ORDER BY p.created_at DESC
    """
    return cur.execute(sql, params).fetchall()

rows = load_products(id_col, sel_id, kw)

# 필터 변경 시 sel_pid 초기화
filter_hash = hashlib.md5(str((id_col, sel_id, kw, per_page)).encode()).hexdigest()
if st.session_state.get("_filter_hash") != filter_hash:
    st.session_state.pop("sel_pid", None)
    st.session_state["_filter_hash"] = filter_hash

## ─────────────────────────────────────
#   페이지 나누기
## ─────────────────────────────────────
page_cnt = max(1, math.ceil(len(rows) / per_page))
page_num = st.number_input("페이지", 1, page_cnt, 1, key="page_num")
view = rows[(page_num - 1) * per_page : page_num * per_page]

# sel_pid 유효성 확인
sel_pid = st.session_state.get("sel_pid")
if sel_pid and not any(r[0] == sel_pid for r in rows):
    st.session_state.pop("sel_pid", None)
    sel_pid = None

## ─────────────────────────────────────
#   카드 목록
## ─────────────────────────────────────
GRID = 4
for r in range(math.ceil(len(view) / GRID)):
    cols = st.columns(GRID)
    for i in range(GRID):
        idx = r * GRID + i
        if idx >= len(view):
            cols[i].empty(); continue
        pid, pname, loc, thumb, *_ = view[idx]
        with cols[i]:
            img_path = resolve_path(thumb)
            if img_path and os.path.exists(img_path):
                st.image(img_path, width=130)
            else:
                st.markdown("<div style='width:130px;height:130px;border:1px dashed #bbb;display:flex;align-items:center;justify-content:center;font-size:11px'>No<br>Image</div>", unsafe_allow_html=True)
            st.markdown(f"**{pname}**")
            st.caption(f"ID:{pid} ｜ {loc or '-'}")
            if st.button("상세", key=f"card_{pid}"):
                st.session_state["sel_pid"] = pid
                sel_pid = pid

## ─────────────────────────────────────
#   상세 페이지
## ─────────────────────────────────────
if sel_pid:
    st.divider(); st.success(f"선택 상품 ID: {sel_pid} (role={role})")

    imgs = cur.execute("SELECT id, COALESCE(image_path, file_name) AS img, is_main FROM product_images WHERE product_id=?", (sel_pid,)).fetchall()

    st.subheader("📷 이미지 관리")
    if not imgs:
        st.info("이미지가 없습니다. 우측 상단에서 업로드해 주세요.")

    for iid, fn, is_main in imgs:
        c1, c2, c3 = st.columns([3, 1, 1])
        ipath = resolve_path(fn)
        if ipath and os.path.exists(ipath):
            c1.image(ipath, width=120)
        else:
            c1.markdown("<div style='width:120px;height:120px;border:1px dashed #bbb;display:flex;align-items:center;justify-content:center;font-size:10px;'>No Img</div>", unsafe_allow_html=True)

        if role == "inspector":
            if c2.radio("메인", ["", "★"], index=(1 if is_main else 0), key=f"star_{iid}") == "★":
                cur.execute("UPDATE product_images SET is_main=0 WHERE product_id=?", (sel_pid,))
                cur.execute("UPDATE product_images SET is_main=1 WHERE id=?", (iid,))
                con.commit(); st.rerun()
            if c3.button("삭제", key=f"del_{iid}"):
                cur.execute("DELETE FROM product_images WHERE id=?", (iid,))
                con.commit(); st.rerun()

    # 이미지 업로드
    if role == "inspector":
        up = st.file_uploader("새 이미지 추가", ["jpg", "jpeg", "png"], accept_multiple_files=True)
        if up:
            for f in up:
                # 고유 파일명 생성 후 db_images/에 저장
                fname = f"{uuid.uuid4()}.jpg"
                save_path = os.path.join(IMG_DIR, fname)
                Image.open(f).convert("RGB").save(save_path, quality=90)
                # DB 등록 (is_main=0, 업로드 시각 기록)
                cur.execute(
                    "INSERT INTO product_images(product_id, image_path, is_main, uploaded_at) VALUES (?,?,0,?)",
                    (sel_pid, fname, now_str()),
                )
            con.commit()
            st.success(f"{len(up)} 개 이미지 업로드 완료!")
            st.rerun()

    # 제품 정보 수정 / 삭제
    if role == "inspector":
        st.subheader("✏️ 제품 정보")
        p = cur.execute(
            "SELECT product_name, vendor_id, operator_id, location FROM products WHERE id=?",
            (sel_pid,),
        ).fetchone()
        if p:
            pn = st.text_input("제품명", p[0])
            vd = st.text_input("도매처", p[1] or "")
            op = st.text_input("브랜드", p[2] or "")
            lc = st.text_input("로케이션", p[3] or "")
            c1, c2 = st.columns(2)
            if c1.button("💾 저장"):
                cur.execute(
                    "UPDATE products SET product_name=?, vendor_id=?, operator_id=?, location=? WHERE id=?",
                    (pn, vd, op, lc, sel_pid),
                )
                con.commit()
                st.success("수정 완료")
                st.rerun()
            if c2.button("🗑️ 삭제", type="secondary"):
                cur.execute("DELETE FROM product_images WHERE product_id=?", (sel_pid,))
                cur.execute("DELETE FROM skus WHERE product_id=?", (sel_pid,))
                cur.execute("DELETE FROM products WHERE id=?", (sel_pid,))
                con.commit()
                st.success("삭제 완료")
                st.session_state.pop("sel_pid", None)
                st.rerun()