import io
import pandas as pd
import streamlit as st
from google import genai
from xhtml2pdf import pisa

# ==========================================
# 1. 페이지 기본 설정 (로그인 없는 단일 페이지)
# ==========================================
st.set_page_config(
    page_title="소상공인 맞춤형 경영진단 및 컨설팅 매칭 리포트",
    layout="wide",
)

st.title("📊 소상공인 경영진단 및 맞춤형 컨설팅 추천 리포트")
st.caption(
    "축적된 폐업 요인 실태조사 데이터(4.6만건)를 기반으로 AI가 경영 인사이트 및 맞춤 컨설팅 사업을 매칭합니다."
)


# ==========================================
# 2. 엑셀 파일 로드 및 데이터 전처리
# ==========================================
@st.cache_data
def load_excel_data():
    try:
        excel_file = "closure_data.xlsx"
        xls = pd.ExcelFile(excel_file)

        # 시트명/순서 기준 로드
        df_failures = pd.read_excel(xls, sheet_name="1. 폐업실패요인 데이터")
        df_categories = pd.read_excel(xls, sheet_name="2. 카테고리")
        df_consulting = pd.read_excel(xls, sheet_name="3. 컨설팅 분야")

        # 데이터 전처리: 나이대 표시 정제 (예: 60 -> 60대)
        df_failures["나이대_표시"] = df_failures["나이대"].astype(str) + "대"

        # 결측치 제거 및 정제
        df_failures["업종"] = df_failures["업종"].fillna("기타")

        return df_failures, df_categories, df_consulting
    except FileNotFoundError:
        st.error(
            "데이터 파일(closure_data.xlsx)을 찾을 수 없습니다. 깃허브에 올린 파일명을 확인해 주세요."
        )
        return None, None, None
    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        return None, None, None


df_failures, df_categories, df_consulting = load_excel_data()


def convert_html_to_pdf(html_string):
    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_string, dest=result, encoding="utf-8")
    if pisa_status.err:
        return None
    return result.getvalue()


# ==========================================
# 3. 사용자 입력 폼 (개인정보 저장 X, 단순 조건 선택)
# ==========================================
if df_failures is not None:
    st.sidebar.header("📋 상담업체 프로필 선택")

    # 드롭다운 메뉴 구성
    selected_district = st.sidebar.selectbox(
        "자치구", sorted(df_failures["자치구"].dropna().unique())
    )
    selected_industry = st.sidebar.selectbox(
        "업종", sorted(df_failures["업종"].dropna().unique())
    )
    selected_age_display = st.sidebar.selectbox(
        "연령대",
        sorted(
            df_failures["나이대_표시"].unique(),
            key=lambda x: int(x.replace("대", "")),
        ),
    )
    selected_gender = st.sidebar.selectbox(
        "성별", sorted(df_failures["성별"].dropna().unique())
    )

    # API Key 설정 (Secrets 우선, 없을 시 입력받음)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.sidebar.text_input("Gemini API Key", type="password")

    generate_btn = st.sidebar.button("🚀 진단 리포트 생성하기", use_container_width=True)

    # ==========================================
    # 4. 데이터 필터링 & Gemini API 호출
    # ==========================================
    if generate_btn:
        if not api_key:
            st.warning("Gemini API Key가 설정되지 않았습니다. Secrets를 확인해 주세요.")
        else:
            # 1. 조건에 맞는 폐업 실패요인 데이터 필터링
            filtered_failures = df_failures[
                (df_failures["자치구"] == selected_district)
                & (df_failures["업종"] == selected_industry)
                & (df_failures["나이대_표시"] == selected_age_display)
                & (df_failures["성별"] == selected_gender)
            ]

            # 조건 검색 결과가 적을 경우 범위 확장 (동일 업종 전체 데이터)
            is_fallback = False
            if filtered_failures.empty:
                filtered_failures = df_failures[df_failures["업종"] == selected_industry]
                is_fallback = True

            # SWOT 코드별 그룹화 및 텍스트 구성
            swot_summary = ""
            if not filtered_failures.empty:
                # 데이터가 너무 많을 경우 상위 15건 샘플링하여 텍스트화
                sample_df = filtered_failures.head(20)
                for idx, row in sample_df.iterrows():
                    swot_summary += f"- [{row['코드']}] {row['항목']}: {row['내용']} (세부사례: {row['추가내용'] if pd.notna(row['추가내용']) else '없음'})\n"

            # 3번 시트 컨설팅 지원사업 목록 텍스트화
            consulting_list_text = ""
            for idx, row in df_consulting.iterrows():
                consulting_list_text += (
                    f"- [{row['항목']}] {row['분야']} > {row['세부 분야']}\n"
                )

            # 프롬프트 구성 (전문가 페르소나 및 정교한 규칙 지정)
            prompt = f"""
            당신은 소상공인 지원사업의 경영컨설팅 및 데이터 분석 전문가입니다.
            46,000여 건의 실제 소상공인 폐업 조사 데이터베이스에서 추출된 아래 자료를 바탕으로, 상담 고객을 위한 객관적이고 논리적인 [경영 진단 및 맞춤 컨설팅 추천 리포트]를 작성하세요.

            [상담 고객 프로필]
            - 자치구: {selected_district} | 업종: {selected_industry} | 연령대: {selected_age_display} | 성별: {selected_gender}
            {"* 참고: 해당 정밀 조건 데이터 수가 적어 동일 업종 전체의 종합 폐업 데이터 경향성을 분석에 반영했습니다." if is_fallback else ""}

            [실제 축적된 동종 유형의 폐업 SWOT 및 실패 요인 사례]
            {swot_summary}

            [자사(기관)에서 제공 중인 실제 컨설팅 지원사업 목록]
            {consulting_list_text}

            [리포트 작성 지시사항]
            1. **동종 유형 폐업 원인 종합 진단**: 제공된 SWOT 실패 요인을 분석하여, 이 유형의 소상공인들이 주로 겪는 경영 위기 패턴(약점 및 위협요인)을 데이터에 기반하여 설명하세요.
            2. **예상 보완점 및 경영 인사이트**: 단순 자금(보증) 지원만으로는 해결되지 않는 핵심 경영 위험 요인을 지적하고, 우선적으로 개선해야 할 전략적 보완점을 제시하세요.
            3. **★ 맞춤형 컨설팅 지원사업 추천 (가장 중요)**: [자사 제공 컨설팅 지원사업 목록] 중에서 이 업체의 약점과 위협을 극복하는 데 가장 직결되는 컨설팅 분야/세부터겟 2~3개를 명확히 지목하고, 왜 이 컨설팅이 필요한지 논리적 사유를 함께 작성하세요.
            4. **격식 및 톤앤매너**: 소상공인 사장님에게 전달되는 전문 기관의 공식 리포트 어조(~하오니, ~를 권장합니다)로 단정하게 작성하세요. 개인정보는 일절 언급하지 마세요.
            """

            with st.spinner("46,000건의 데이터베이스와 매칭하여 맞춤 리포트를 생성 중입니다..."):
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                    )
                    report_text = response.text

                    st.success("경영 진단 및 컨설팅 지원사업 매칭 리포트가 생성되었습니다!")

                    # 화면 출력
                    st.markdown("---")
                    st.subheader(
                        f"📌 [{selected_district} / {selected_industry} / {selected_age_display} {selected_gender}] 맞춤 경영 진단서"
                    )
                    st.write(report_text)

                    # 인쇄용 HTML (A4 출력 스타일)
                    html_content = f"""
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <style>
                            body {{ font-family: Helvetica, Arial, sans-serif; padding: 20px; line-height: 1.6; color: #333; }}
                            h1 {{ color: #1E3A8A; border-bottom: 2px solid #1E3A8A; padding-bottom: 8px; font-size: 18px; }}
                            .info-box {{ background-color: #F3F4F6; padding: 12px; border-radius: 5px; margin-bottom: 15px; font-size: 11px; }}
                            .content {{ font-size: 11px; white-space: pre-wrap; }}
                        </style>
                    </head>
                    <body>
                        <h1>소상공인 경영진단 및 맞춤 컨설팅 매칭 리포트</h1>
                        <div class="info-box">
                            <strong>상담 고객 프로필:</strong> {selected_district} | {selected_industry} | {selected_age_display} | {selected_gender}<br>
                            <strong>분석 기반:</strong> 소상공인 폐업실태 조사 데이터베이스 기반 자동 추출<br>
                            <strong>발급 안내:</strong> 본 리포트는 개인정보를 저장하지 않는 일회성 맞춤 진단서입니다.
                        </div>
                        <div class="content">
                            {report_text}
                        </div>
                    </body>
                    </html>
                    """

                    pdf_data = convert_html_to_pdf(html_content)

                    if pdf_data:
                        st.download_button(
                            label="🖨️ PDF 리포트 다운로드 / 인쇄",
                            data=pdf_data,
                            file_name=f"Report_{selected_district}_{selected_industry}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )

                except Exception as e:
                    st.error(f"리포트 생성 중 오류가 발생했습니다: {e}")
