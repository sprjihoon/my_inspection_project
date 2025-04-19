import streamlit as st
from common import init_db, get_connection

def main():
    st.set_page_config(page_title="AI 의류검수시스템11", layout="wide")
    init_db()

    if 'user_role' not in st.session_state:
        st.session_state['user_role'] = None
        st.session_state['user_id'] = None

    st.title("AI 의류검수시스템11")
    st.write("사이드바에서 원하는 기능을 선택하세요.")

    if st.session_state["user_role"] is None:
        st.subheader("로그인")
        username = st.text_input("아이디")
        password = st.text_input("비밀번호", type="password")
        if st.button("로그인"):
            con = get_connection()
            cur = con.cursor()
            row = cur.execute("SELECT id, role FROM users WHERE username=? AND password=?", (username, password)).fetchone()
            if row:
                st.session_state["user_id"] = row[0]
                st.session_state["user_role"] = row[1]
                st.success(f"로그인 성공! 권한: {row[1]}")
                st.rerun()
            else:
                st.error("로그인 실패")
    else:
        st.write(f"현재 로그인: {st.session_state['user_role']} (UserID={st.session_state['user_id']})")
        if st.button("로그아웃"):
            st.session_state["user_role"] = None
            st.session_state["user_id"] = None
            st.rerun()

if __name__ == "__main__":
    main()
