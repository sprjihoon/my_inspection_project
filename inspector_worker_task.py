import streamlit as st
import pandas as pd
from datetime import datetime
from common import get_connection, now_str

con = get_connection()
cur = con.cursor()

# --------------------------------------------------
# 유틸
# --------------------------------------------------

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

# --------------------------------------------------
# 메인
# --------------------------------------------------

def main():
    st.title("작업자 – 바코드 기반 작업 기록")

    # 권한 체크
    if st.session_state.get("user_role") != "worker":
        st.warning("접근 권한이 없습니다. (작업자 전용)")
        st.stop()

    # 세션 기본값
    defaults = {
        "scan_qty": 1,            # 정상 수량 입력값
        "latest_result": None,    # 전표 정보 튜플
        "last_barcode": "",       # 마지막 스캔한 바코드
        "scan_start_time": None,  # 작업 시작 시각
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # --------------------------------------------------
    # 바코드 입력
    # --------------------------------------------------
    st.subheader("📷 바코드 스캔")
    barcode_input = st.text_input("바코드를 입력 또는 스캔하세요")

    if barcode_input and barcode_input != st.session_state["last_barcode"]:
        today_like = f"%{get_today()}%"
        today_row = cur.execute(
            """
            SELECT ir.id, ir.product_id, p.product_name, p.operator_id, p.location,
                   ir.total_qty, ir.status, ir.inspected_at
              FROM inspection_results ir
              JOIN products p ON ir.product_id = p.id
             WHERE ir.barcode = ? AND ir.inspected_at LIKE ?
             ORDER BY ir.id DESC LIMIT 1
            """,
            (barcode_input, today_like),
        ).fetchone()

        if today_row:
            st.session_state.update(
                {
                    "latest_result": today_row,
                    "scan_qty": 1,
                    "last_barcode": barcode_input,
                    "scan_start_time": datetime.now(),
                }
            )
            st.rerun()
        else:
            st.warning("오늘 전표를 찾을 수 없습니다. 최근 전표를 검색해 주세요.")

    # --------------------------------------------------
    # 전표 정보 & 입력
    # --------------------------------------------------
    result = st.session_state["latest_result"]
    if result:
        (
            ir_id,
            pid,
            pname,
            brand_id,
            location,
            total_qty,
            _status,
            inspected_at,
        ) = result

        # 누적 작업량
        total_done, total_defect = cur.execute(
            "SELECT COALESCE(SUM(repaired_qty),0), COALESCE(SUM(additional_defect_qty),0) FROM work_orders WHERE inspection_id=?",
            (ir_id,),
        ).fetchone()

        # 전표 요약
        st.markdown(f"**제품명:** {pname}")
        st.markdown(f"**위치:** {location}")
        st.markdown(f"**전표:** {brand_id}_{inspected_at[:10].replace('-', '')}")
        st.markdown(f"**검수 수량:** {total_qty}")

        # 작업자별 현황
        st.divider()
        my_id = st.session_state["user_id"]
        workers = cur.execute(
            """
            SELECT worker_id, SUM(repaired_qty), SUM(additional_defect_qty)
              FROM work_orders
             WHERE inspection_id=?
             GROUP BY worker_id
            """,
            (ir_id,),
        ).fetchall()
        for wid, normal, defect in workers:
            color = "red" if wid == my_id else "blue"
            st.markdown(
                f"<span style='color:{color}'>작업자 {wid}: {normal or 0} 정상 / {defect or 0} 추가불량</span>",
                unsafe_allow_html=True,
            )

        # ------------------------------------------------
        # 수량 입력 (깜빡임 제거: key 사용)
        # ------------------------------------------------
        st.subheader("작업 수량 입력")
        scan_qty = st.number_input(
            "정상 수량",
            min_value=0,
            step=1,
            key="scan_qty",  # 👉 세션과 자동 연동
        )
        defect_qty = st.number_input("추가 불량", min_value=0, step=1, key="defect_qty")

        # 남은 수량 실시간 계산
        remaining = total_qty - total_done - total_defect - scan_qty
        st.info(f"남은 수량: {remaining}")

        if scan_qty + defect_qty + total_done + total_defect > total_qty:
            st.error("합계가 검수 수량을 초과합니다!")
            st.stop()

        # 작업 상세
        difficulty = st.selectbox("작업 난이도", ["양품화1", "양품화2", "프리미엄양품화1"])
        extras = st.multiselect("추가 작업", ["스팀", "수선", "세탁"])
        comment = st.text_area("작업 코멘트")

        # 저장
        if st.button("✅ 작업 완료 저장"):
            # 최소 1장 이상 입력해야 저장 가능
            if scan_qty == 0 and defect_qty == 0:
                st.warning("정상·추가 불량 수량이 모두 0입니다. 최소 1 이상 입력해 주세요.")
                st.stop()

            cur.execute(
                """
                INSERT INTO work_orders
                    (inspection_id, worker_id, additional_defect_qty, repaired_qty,
                     repaired_approved, difficulty, extra_tasks, created_at)
                VALUES (?,?,?,?,0,?,?,?)
                """,
                (
                    ir_id,
                    my_id,
                    defect_qty,
                    scan_qty,
                    difficulty,
                    ",".join(extras),
                    now_str(),
                ),
            )
            con.commit()
            st.success("작업 완료가 저장되었습니다!")
                        # 세션 리셋: scan_qty 는 위젯이 이미 생성된 상태라 직접 재할당하면 오류가 납니다.
            st.session_state.pop("scan_qty", None)            # 제거 후 다음 rerun 에서 defaults 로 초기화
            for k in ["latest_result", "last_barcode", "scan_start_time"]:
                st.session_state[k] = defaults[k]
            st.rerun()

    # --------------------------------------------------
    # 오늘 작업 로그
    # --------------------------------------------------
    st.divider()
    st.subheader("🧑‍🔧 오늘 작업 내역")
    logs = cur.execute(
        """
        SELECT w.inspection_id, u.username, w.repaired_qty, w.additional_defect_qty,
               w.difficulty, w.extra_tasks, w.created_at
          FROM work_orders w
          JOIN users u ON w.worker_id = u.id
         WHERE DATE(w.created_at)=DATE(?)
         ORDER BY w.created_at DESC
         LIMIT 20
        """,
        (get_today(),),
    ).fetchall()
    df = pd.DataFrame(
        logs,
        columns=["전표", "작업자", "정상", "추가불량", "난이도", "추가작업", "시간"],
    )
    st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
