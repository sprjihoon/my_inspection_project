import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from common import get_connection

con = get_connection()
cur = con.cursor()

# --------------------------------------------------
# 유틸
# --------------------------------------------------

def today_dt() -> datetime:
    return datetime.now()

def get_today_str() -> str:
    return today_dt().strftime("%Y-%m-%d")

def first_day_of_month(dt: datetime) -> str:
    return dt.replace(day=1).strftime("%Y-%m-%d")

def first_day_prev_month(dt: datetime) -> str:
    prev = dt.replace(day=1) - timedelta(days=1)
    return prev.replace(day=1).strftime("%Y-%m-%d")

def last_day_prev_month(dt: datetime) -> str:
    return (dt.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

def prune_old_records(worker_id: int):
    """90일(≈3 개월) 초과된 work_orders 자동 삭제"""
    limit_date = (today_dt() - timedelta(days=90)).strftime("%Y-%m-%d")
    cur.execute(
        "DELETE FROM work_orders WHERE worker_id=? AND DATE(created_at) < DATE(?)",
        (worker_id, limit_date),
    )
    con.commit()

# --------------------------------------------------
# 메인
# --------------------------------------------------

def main():
    st.title("작업자 – 내 작업 리스트 · 수정")

    # 권한 체크
    if st.session_state.get("user_role") != "worker":
        st.warning("접근 권한이 없습니다. (작업자 전용)")
        st.stop()

    my_id = st.session_state["user_id"]

    # ▶︎ 90일 초과 기록 자동 정리
    prune_old_records(my_id)

    # ---------------- 기간 필터 ----------------
    period = st.radio(
        "조회 기간",
        ["오늘", "어제", "이번달", "지난달", "최근 7일", "최근 30일", "날짜 지정"],
        horizontal=True,
    )

    where = ""
    params = [my_id]
    today = get_today_str()
    now_dt = today_dt()

    if period == "오늘":
        where = "AND DATE(w.created_at)=DATE(?)"
        params.append(today)
    elif period == "어제":
        where = "AND DATE(w.created_at)=DATE(?,'-1 day')"
        params.append(today)
    elif period == "이번달":
        first = first_day_of_month(now_dt)
        where = "AND DATE(w.created_at) >= DATE(?)"
        params.append(first)
    elif period == "지난달":
        first_prev = first_day_prev_month(now_dt)
        last_prev  = last_day_prev_month(now_dt)
        where = "AND DATE(w.created_at) BETWEEN DATE(?) AND DATE(?)"
        params.extend([first_prev, last_prev])
    elif period == "최근 7일":
        where = "AND w.created_at>=DATE(?,'-6 day')"
        params.append(today)
    elif period == "최근 30일":
        where = "AND w.created_at>=DATE(?,'-29 day')"
        params.append(today)
    elif period == "날짜 지정":
        col1, col2 = st.columns(2)
        start = col1.date_input("시작일", value=now_dt-timedelta(days=6))
        end   = col2.date_input("종료일", value=now_dt)
        if start > end:
            st.error("시작일이 종료일보다 클 수 없습니다.")
            st.stop()
        where = "AND DATE(w.created_at) BETWEEN DATE(?) AND DATE(?)"
        params.extend([start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")])

    # ---------------- 데이터 조회 ----------------
    rows = cur.execute(
        f"""
        SELECT w.id, w.inspection_id, p.product_name,
               w.repaired_qty, w.additional_defect_qty,
               w.difficulty, w.extra_tasks, w.created_at
          FROM work_orders w
          JOIN inspection_results ir ON w.inspection_id = ir.id
          JOIN products p ON ir.product_id = p.id
         WHERE w.worker_id=? {where}
         ORDER BY w.created_at DESC
        """,
        tuple(params),
    ).fetchall()

    if not rows:
        st.info("해당 기간에 작업 내역이 없습니다.")
        return

    df = pd.DataFrame(
        rows,
        columns=[
            "작업ID", "전표ID", "상품명", "정상", "추가불량",
            "난이도", "추가작업", "시간",
        ],
    )

    st.subheader("내 작업 내역 (수정 가능, 삭제 불가)")
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")

    if st.button("💾 수정 저장"):
        for _, r in edited.iterrows():
            cur.execute(
                """
                UPDATE work_orders
                   SET repaired_qty=?, additional_defect_qty=?, difficulty=?, extra_tasks=?
                 WHERE id=? AND worker_id=?
                """,
                (
                    int(r["정상"]),
                    int(r["추가불량"]),
                    r["난이도"],
                    r["추가작업"],
                    int(r["작업ID"]),
                    my_id,
                ),
            )
        con.commit()
        st.success("수정 내용이 저장되었습니다!")
        st.rerun()

    # ---------------- 통계 요약 ----------------
    tot_normal = edited["정상"].sum()
    tot_defect = edited["추가불량"].sum()
    col1, col2 = st.columns(2)
    col1.metric("총 정상 처리", f"{tot_normal} 장")
    col2.metric("총 추가불량", f"{tot_defect} 장")

if __name__ == "__main__":
    main()
