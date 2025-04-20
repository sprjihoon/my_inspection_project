################################################################################
# app.py  –  프로젝트 메인 엔트리 (Streamlit 멀티페이지)
################################################################################
import streamlit as st
from common import init_db, get_connection

# ───────── 초기 설정 ─────────
st.set_page_config(
    page_title="AI 의류검수 시스템",
    page_icon="👕",
    layout="wide",
)

# DB 준비
init_db()
con = get_connection()

# ───────── 세션 기본값 ─────────
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None     # 'admin' / 'operator' / 'inspector' / 'worker'
    st.session_state["user_id"]   = None     # users.id

# ───────── 로그인 화면 ─────────
def login_form():
    st.subheader("🔐 로그인")
    username = st.text_input("아이디")
    password = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        cur = con.cursor()
        row = cur.execute(
            "SELECT id, role FROM users WHERE username=? AND password=?",
            (username, password),
        ).fetchone()
        if row:
            st.session_state["user_id"]   = row[0]
            st.session_state["user_role"] = row[1]
            st.success(f"로그인 성공! 권한: {row[1]}")
            st.rerun()
        else:
            st.error("로그인 실패 – 아이디/비밀번호 확인")

# ───────── 메인 ─────────
def main():
    st.title("AI 의류검수 시스템 – 홈")

    if st.session_state["user_role"] is None:
        # 아직 로그인 안 했으면 로그인 폼만 보여줌
        login_form()
        return

    # 로그인 후 첫 화면
    st.sidebar.success(f"권한: {st.session_state['user_role']}")
    st.sidebar.write("사이드바에서 페이지를 선택하세요.")

    st.write(
        """
        ### 📊 대시보드 / 안내
        * 좌측 사이드바에서 각 역할별 페이지로 이동할 수 있습니다.
        * 로그인 상태는 페이지 이동 후에도 유지됩니다.
        """
    )
    if st.button("로그아웃"):
        st.session_state["user_role"] = None
        st.session_state["user_id"]   = None
        st.rerun()       # Streamlit ≥1.23 → st.rerun()도 가능

# ───────── 실행 ─────────
if __name__ == "__main__":
    main()