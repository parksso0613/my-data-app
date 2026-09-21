import datetime
import pandas as pd
import plotly.express as px
import pytz
import requests
import streamlit as st

# ==========================================
# 1. 기본 페이지 설정
# ==========================================
st.set_page_config(page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide")

st.title("🎬 일별 박스오피스 조회")


# ==========================================
# 2. 날짜 계산 및 데이터 불러오기 함수
# ==========================================
def get_yesterday_kst():
    """한국 시간(KST) 기준으로 '어제' 날짜 객체를 반환합니다."""
    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.datetime.now(kst)
    yesterday = now_kst - datetime.timedelta(days=1)
    return yesterday.date()


@st.cache_data(ttl=3600)  # 1시간 동안 같은 날짜 데이터 기억
def fetch_daily_boxoffice(target_date_str):
    """KOBIS API를 호출하여 지정된 날짜(YYYYMMDD)의 박스오피스 데이터를 가져옵니다."""
    api_key = st.secrets.get("KOBIS_KEY")

    if not api_key:
        return None, "secrets.toml 파일에 'KOBIS_KEY'가 설정되지 않았습니다."

    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date_str}

    try:
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # faultInfo 오류 체크
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "인증키 또는 요청 변수가 잘못되었습니다."
            )
            return None, f"API 오류 (faultInfo): {message}"

        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 영화 목록 데이터가 비어 있는 경우
        if not daily_list:
            return None, "그날은 아직 집계 전입니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 실패: {e}"


# ==========================================
# 3. 사이드바 날짜 선택 UI
# ==========================================
yesterday_date = get_yesterday_kst()

st.sidebar.header("🗓️ 날짜 선택")
selected_date = st.sidebar.date_input(
    label="조회할 날짜를 선택하세요",
    value=yesterday_date,  # 기본값: 어제
    max_value=yesterday_date,  # 선택 가능 최대 날짜: 어제
    min_value=datetime.date(2004, 1, 1),  # KOBIS 제공 시작일 부근
)

# API 규격에 맞는 YYYYMMDD 문자열 생성
target_date_str = selected_date.strftime("%Y%m%d")
formatted_date = selected_date.strftime("%Y년 %m월 %d일")

# ==========================================
# 4. 데이터 불러오기 및 예외 처리
# ==========================================
raw_data, error_msg = fetch_daily_boxoffice(target_date_str)

if error_msg:
    if error_msg == "그날은 아직 집계 전입니다.":
        st.info(f"💡 **{formatted_date}**: 그날은 아직 집계 전입니다.")
    else:
        st.error("데이터를 불러오지 못했습니다. 아래 내용을 확인해 주세요.")
        st.warning(f"📌 **상세 사유**: {error_msg}")
        st.info(
            """
            💡 **확인 가이드**
            1. Streamlit Cloud의 **Secrets 설정**에 `KOBIS_KEY`가 올바르게 입력되어 있는지 확인하세요.
            2. KOBIS 발급 Key가 활성화 상태인지 확인해 주세요.
            3. 네트워크 상태를 점검하거나 잠시 후 다시 시도해 주세요.
            """
        )
else:
    # --------------------------------------
    # 5. 데이터 전처리
    # --------------------------------------
    df = pd.DataFrame(raw_data)

    # 문자열 수치를 정수형(int)으로 변환
    numeric_columns = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
        "showCnt",
    ]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 순위 기준 정렬
    df = df.sort_values(by="rank").reset_index(drop=True)

    # 5-1. 순위 증감(rankInten) 텍스트/화살표 변환 함수
    def format_rank_inten(row):
        # 신규 진입 영화 처리 (rankOldAndNew 가 "NEW"인 경우)
        if row.get("rankOldAndNew") == "NEW":
            return "🆕"

        inten = row["rankInten"]
        if inten > 0:
            return f"🔺 +{inten}"
        elif inten < 0:
            return f"🔹 {inten}"
        else:
            return "-"

    df["순위변동"] = df.apply(format_rank_inten, axis=1)

    # 5-2. 누적관객 100만 명 이상 시 영화명 뒤에 🏆 트로피 추가
    def format_movie_title(row):
        title = row["movieNm"]
        if row["audiAcc"] >= 1_000_000:
            return f"{title} 🏆"
        return title

    df["표시영화명"] = df.apply(format_movie_title, axis=1)

    st.subheader(f"📅 기준일: {formatted_date}")

    # --------------------------------------
    # 6. 1위 영화 지표 카드
    # --------------------------------------
    top_1 = df.iloc[0]

    st.markdown("### 🏆 박스오피스 1위")
    col1, col2, col3 = st.columns(3)

    col1.metric(label="🎬 1위 영화명", value=top_1["표시영화명"])
    col2.metric(label="👤 일일 관객수", value=f"{top_1['audiCnt']:,} 명")
    col3.metric(label="🍿 누적 관객수", value=f"{top_1['audiAcc']:,} 명")

    st.divider()

    # --------------------------------------
    # 7. 상위 5개 영화 관객수 막대그래프
    # --------------------------------------
    st.markdown("### 📊 관객수 상위 5개 영화")
    top_5_df = df.head(5)

    fig = px.bar(
        top_5_df,
        x="표시영화명",
        y="audiCnt",
        text_auto=",",
        labels={"표시영화명": "영화명", "audiCnt": "일일 관객수 (명)"},
        color="audiCnt",
        color_continuous_scale="Blues",
    )
    fig.update_layout(xaxis_title="", yaxis_title="관객수(명)", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------
    # 8. 전체 박스오피스 순위 표
    # --------------------------------------
    st.markdown("### 📋 전체 박스오피스 순위")

    # 표에 출력할 컬럼 지정 및 컬럼명 가독성 개선
    display_df = df[
        [
            "rank",
            "순위변동",
            "표시영화명",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt",
        ]
    ].copy()

    display_df.columns = [
        "순위",
        "순위 변동",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "관객수": st.column_config.NumberColumn(format="%d 명"),
            "누적관객": st.column_config.NumberColumn(format="%d 명"),
            "스크린수": st.column_config.NumberColumn(format="%d 개"),
        },
    )
