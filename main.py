import datetime
import requests
import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

# ==========================================
# 1. 기본 페이지 설정
# ==========================================
st.set_page_config(
    page_title="어제 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제의 일별 박스오피스")


# ==========================================
# 2. 날짜 계산 및 데이터 불러오기 함수
# ==========================================
def get_yesterday_kst():
    """배포 서버의 시계와 상관없이 '한국 시간(KST)' 기준으로 어제 날짜(YYYYMMDD)를 계산합니다."""
    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.datetime.now(kst)
    yesterday = now_kst - datetime.timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


@st.cache_data(ttl=3600)  # 1시간(3600초) 동안 동일 날짜 요청에 대해 결과를 캐싱합니다.
def fetch_daily_boxoffice(target_date):
    """KOBIS API를 호출하여 해당 날짜의 박스오피스 데이터를 가져옵니다."""
    # Secrets에서 발급받은 KOBIS_KEY를 가져옵니다.
    api_key = st.secrets.get("KOBIS_KEY")

    if not api_key:
        return None, "secrets.toml 파일에 'KOBIS_KEY'가 설정되지 않았습니다."

    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, timeout=10)

        # HTTP 응답 상태 코드가 200이 아닌 경우
        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # 인증키 오류 등이 발생하면 200 OK와 함께 faultInfo가 전달됩니다.
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "인증키 또는 요청 변수가 잘못되었습니다."
            )
            return None, f"API 오류 (faultInfo): {message}"

        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 영화 목록 데이터가 비어 있는 경우
        if not daily_list:
            return None, "해당 날짜의 박스오피스 데이터가 비어 있습니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 실패: {e}"


# ==========================================
# 3. 메인 로직 실행
# ==========================================
target_date = get_yesterday_kst()
formatted_date = f"{target_date[:4]}년 {target_date[4:6]}월 {target_date[6:]}일"

raw_data, error_msg = fetch_daily_boxoffice(target_date)

# 에러가 발생한 경우 안내 메시지 출력
if error_msg:
    st.error("데이터를 불러오지 못했습니다. 아래 내용을 확인해 주세요.")
    st.warning(f"📌 **상세 사유**: {error_msg}")
    st.info(
        """
        💡 **확인 가이드**
        1. Streamlit Cloud의 **Secrets 설정**에 `KOBIS_KEY`가 올바르게 입력되어 있는지 확인하세요.
        2. KOBIS 영화관입장권통합전산망에서 발급받은 Key가 활성화 상태인지 확인해 주세요.
        3. 네트워크 연결 상태를 점검하거나 잠시 후 다시 시도해 주세요.
        """
    )
else:
    # --------------------------------------
    # 4. 데이터 전처리 (문자열 -> 숫자 변환)
    # --------------------------------------
    df = pd.DataFrame(raw_data)

    # API 결과의 문자열 수치를 정수형(int)으로 변환
    numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 순위 기준으로 데이터 정렬
    df = df.sort_values(by="rank").reset_index(drop=True)

    st.subheader(f"📅 기준일: {formatted_date}")

    # --------------------------------------
    # 5. 1위 영화 하이라이트 (카드 지표)
    # --------------------------------------
    top_1 = df.iloc[0]

    st.markdown("### 🏆 어제 박스오피스 1위")
    col1, col2, col3 = st.columns(3)

    col1.metric(label="🎬 1위 영화명", value=top_1["movieNm"])
    col2.metric(label="👤 어제 관객수", value=f"{top_1['audiCnt']:,} 명")
    col3.metric(label="🍿 누적 관객수", value=f"{top_1['audiAcc']:,} 명")

    st.divider()

    # --------------------------------------
    # 6. 상위 5개 영화 관객수 막대그래프
    # --------------------------------------
    st.markdown("### 📊 관객수 상위 5개 영화")
    top_5_df = df.head(5)

    fig = px.bar(
        top_5_df,
        x="movieNm",
        y="audiCnt",
        text_auto=",",
        labels={"movieNm": "영화명", "audiCnt": "어제 관객수 (명)"},
        color="audiCnt",
        color_continuous_scale="Blues",
    )
    fig.update_layout(xaxis_title="", yaxis_title="관객수(명)", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------
    # 7. 전체 박스오피스 순위 표
    # --------------------------------------
    st.markdown("### 📋 전체 박스오피스 순위")

    # 표시할 컬럼 정리 및 이름 변경
    display_df = df[
        ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
    ].copy()
    display_df.columns = [
        "순위",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

    # 표 출력 (숫자 세 자릿수 콤마 포맷 적용)
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
