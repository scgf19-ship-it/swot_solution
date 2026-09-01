import io
import pandas as pd
import streamlit as st
from google import genai
from xhtml2pdf import pisa

# ==========================================
# 1. 페이지 기본 설정 (로그인 없는 단일 페이지)
# ==========================================
st.set_page_config(
    page_title="소상공인 맞춤형 폐업위험 진단 및 컨설팅 리포트",
    layout="wide",
)

st.title("📊 소상공인 경영진단 및 맞춤형 컨설팅 리포트")
st.caption(
    "축적된 폐업 요인 데이터(SWOT)를 기반으로 AI가 객관적 인사이트 및 보완점을 제시합니다."
)


# ==========================================
# 2. 데이터 로드 (관리자 CSV 파일 연동)
# ==========================================
@st.cache_data
def load_data():
    try:
        # 데이터베이스 역할을 하는 CSV 파일 로드
        df = pd.read_csv("closure_data.csv")
        return df
    except FileNotFoundError:
        st.error(
            "데이터 파일(closure_data.csv)을 찾을 수 없습니다. 경로를 확인해 주세요."
        )
        return None


df = load_data()


# HTML을 PDF 바이너리로 변환하는 함수
def convert_html_to_pdf(html_string):
    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_string, dest=result, encoding="utf-8")
    if pisa_status.err:
        return None
    return result.getvalue()


# ==========================================
# 3. 사용자 입력 폼 (개인정보 저장 X, 단순 조건 선택)
# ==========================================
if df is not None:
    st.sidebar.header("📋 상담업체 유형 선택")

    # CSV 데이터 내의 유일한 값들을 추출하여 드롭다운 구성
    selected_district = st.sidebar.selectbox(
        "자치구", sorted(df["자치구"].unique())
    )
    selected_industry = st.sidebar.selectbox(
        "업종", sorted(df["업종"].unique())
    )
    selected_age = st.sidebar.selectbox(
        "연령대", sorted(df["연령대"].unique())
    )
    selected_gender = st.sidebar.selectbox(
        "성별", sorted(df["성별"].unique())
    )

    # Gemini API 키 입력 (Streamlit Secrets 또는 사용자 입력)
    # 실제 배포 시에는 Streamlit Cloud Secrets(st.secrets["GEMINI_API_KEY"])에 설정하면 편리합니다.
    api_key = st.sidebar.text_input(
        "Gemini API Key", type="password", help="API 키는 저장되지 않습니다."
    )

    # 리포트 생성 버튼
    generate_btn = st.sidebar.button("🚀 리포트 생성하기", use_container_width=True)

    # ==========================================
    # 4. 데이터 필터링 & Gemini API 호출
    # ==========================================
    if generate_btn:
        if not api_key:
            st.warning("Gemini API Key를 입력해 주세요.")
        else:
            # 선택한 조건에 맞는 데이터 매칭
            filtered_df = df[
                (df["자치구"] == selected_district)
                & (df["업종"] == selected_industry)
                & (df["연령대"] == selected_age)
                & (df["성별"] == selected_gender)
            ]

            # 조건에 매칭되는 데이터 텍스트 생성
            if not filtered_df.empty:
                data_summary = filtered_df.to_string(index=False)
            else:
                data_summary = f"{selected_district} {selected_industry} {selected_age} {selected_gender} 유형의 전체 평균 폐업 경향성 데이터를 참조함."

            # AI 프롬프트 구성 (개인식별정보 전혀 없이 조건과 SWOT 통계만 전달)
            prompt = f"""
            당신은 소상공인 지원사업의 경영컨설팅 및 데이터 분석 전문가입니다.
            아래에 제공된 [축적 데이터]를 바탕으로, 상담 고객의 유형에 맞춘 객관적이고 논리적인 진단 리포트를 작성하세요.

            [상담업체 유형]
            - 자치구: {selected_district}
            - 업종: {selected_industry}
            - 연령대: {selected_age}
            - 성별: {selected_gender}

            [축적된 동종 유형 폐업 SWOT 데이터]
            {data_summary}

            [작성 지시사항]
            1. 동종 유형의 주요 폐업 요인 분석 (SWOT 기반 객관적 데이터 제시)
            2. 현재 고객 유형에서 예상되는 핵심 약점(Weakness) 및 위협(Threat) 보완점
            3. 자금 지원(보증) 외에 경영 체질 개선을 위해 반드시 연계해야 할 맞춤형 컨설팅 및 경영지원 사업 추천
            4. 단정한 리포트 형태로 작성할 것 (개인정보는 절대 언급하지 말 것).
            """

            with st.spinner("데이터 기반 AI 리포트를 생성 중입니다..."):
                try:
                    # Google GenAI SDK 호출
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                    )
                    report_text = response.text

                    # ==========================================
                    # 5. 리포트 화면 출력 및 HTML/PDF 구성
                    # ==========================================
                    st.success("진단 리포트 생성이 완료되었습니다!")

                    # 화면 표시용
                    st.markdown("---")
                    st.subheader(
                        f"📌 [{selected_district} / {selected_industry} / {selected_age} {selected_gender}] 맞춤 진단서"
                    )
                    st.write(report_text)

                    # 인쇄용 HTML 템플릿 생성 (PDF 변환용)
                    html_content = f"""
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <style>
                            body {{ font-family: Helvetica, Arial, sans-serif; padding: 20px; line-height: 1.6; }}
                            h1 {{ color: #1E3A8A; border-bottom: 2px solid #1E3A8A; padding-bottom: 10px; }}
                            .info-box {{ background-color: #F3F4F6; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                            .content {{ font-size: 12px; white-space: pre-wrap; }}
                        </style>
                    </head>
                    <body>
                        <h1>소상공인 경영진단 및 맞춤 컨설팅 리포트</h1>
                        <div class="info-box">
                            <strong>상담 유형:</strong> {selected_district} | {selected_industry} | {selected_age} | {selected_gender}<br>
                            <strong>진단 일자:</strong> 미저장 일회성 발급 리포트
                        </div>
                        <div class="content">
                            {report_text}
                        </div>
                    </body>
                    </html>
                    """

                    # PDF 파일 생성 (메모리에서 일회성 생성)
                    pdf_data = convert_html_to_pdf(html_content)

                    if pdf_data:
                        st.download_button(
                            label="🖨️ PDF 리포트 다운로드 / 인쇄",
                            data=pdf_data,
                            file_name=f"Consulting_Report_{selected_district}_{selected_industry}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )

                except Exception as e:
                    st.error(f"리포트 생성 중 오류가 발생했습니다: {e}")