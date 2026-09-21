import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

# 인증키는 비밀 금고(secrets)에서 불러온다 — 코드에 직접 쓰지 않는다
API_KEY = st.secrets["KOBIS_KEY"]
URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# '어제'를 한국 시간 기준으로 계산한다 (배포 서버의 시계는 한국 시간이 아니다)
KST = datetime.timezone(datetime.timedelta(hours=9))
yesterday = datetime.datetime.now(KST).date() - datetime.timedelta(days=1)

# 날짜 선택 달력 추가
selected_date = st.date_input(
    "조회할 날짜를 선택해 주세요",
    value=yesterday,
    max_value=yesterday,
    help="오늘 및 미래 날짜는 선택할 수 없습니다."
)
target_dt = selected_date.strftime("%Y%m%d")

@st.cache_data(ttl=3600)  # 같은 날짜는 한 시간 동안 기억해 두고 API를 다시 부르지 않는다
def fetch_boxoffice(date_str):
    """KOBIS API에서 해당 날짜의 일별 박스오피스를 받아 온다."""
    params = {"key": API_KEY, "targetDt": date_str}
    res = requests.get(URL, params=params, timeout=10)
    res.raise_for_status()
    return res.json()

st.title("🎬 박스오피스 조회")
st.caption(f"선택한 날짜: {selected_date}")

try:
    data = fetch_boxoffice(target_dt)
except requests.RequestException:
    st.error("서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 새로고침해 주세요.")
    st.stop()

# 인증키가 틀리면 상태코드는 200이지만 faultInfo 상자가 온다
if "faultInfo" in data:
    st.error(f"API가 오류를 돌려주었습니다: {data['faultInfo'].get('message', '')}")
    st.info("비밀 금고(secrets)의 KOBIS_KEY 값이 올바른지 확인해 주세요.")
    st.stop()

movies = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 영화 목록이 비어서 오면 — 아직 집계 전인 날짜다
if not movies:
    st.warning("그날은 아직 집계 전입니다.")
    st.stop()

df = pd.DataFrame(movies)

# 숫자가 글자로 오므로 숫자로 바꿔야 정렬과 그래프에 쓸 수 있다
for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col])


def format_rank_change(val):
    if val > 0:
        return f"🔺 +{val}"
    elif val < 0:
        return f"🔹 {val}"
    return "-"


df["전날대비"] = df["rankInten"].apply(format_rank_change)
# 100만 명 이상 시 🏆 트로피 표기 (1_000_000 구문 수정)
df["영화명_표시"] = df.apply(
    lambda r: f"{r['movieNm']} 🏆" if r["audiAcc"] >= 1_000_000 else r["movieNm"],
    axis=1,
)

# 1위 영화는 지표 카드 세 장으로 크게
top = df.sort_values("rank").iloc[0]
st.subheader(f"🥇 1위 — {top['영화명_표시']}")
c1, c2, c3 = st.columns(3)
c1.metric("선택일 관객수", f"{top['audiCnt']:,}명")
c2.metric("누적 관객수", f"{top['audiAcc']:,}명")
c3.metric("스크린수", f"{top['scrnCnt']:,}개")

# 전체 순위표
st.subheader(f"📋 {selected_date} 순위표")
table = df.sort_values("rank")[
    ["rank", "전날대비", "영화명_표시", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
]
table.columns = ["순위", "전날대비", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]
st.dataframe(table, hide_index=True, width="stretch")

# 관객수 상위 5편은 막대그래프로
st.subheader("📊 관객수 상위 5편")
top5 = df.sort_values("audiCnt", ascending=False).head(5)
fig = px.bar(
    top5,
    x="영화명_표시",
    y="audiCnt",
    labels={"영화명_표시": "영화명", "audiCnt": "선택일 관객수"},
)
st.plotly_chart(fig, width="stretch")
