import io
import os
import urllib.request
import pandas as pd
import streamlit as st
from google import genai
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ==========================================
# 0. Pretendard (Bold / Light) PDF 폰트 로드 및 안전 등록
# ==========================================
@st.cache_resource
def register_pretendard_fonts():
    bold_registered = False
    light_registered = False

    # 1. Pretendard-Bold (제목용)
    bold_path = "Pretendard-Bold.ttf"
    if os.path.exists(bold_path):
        try:
            pdfmetrics.registerFont(TTFont('PretendardBold', bold_path))
            bold_registered = True
        except Exception:
            pass

    # 2. Pretendard-Light (본문용)
    light_path = "Pretendard-Light.ttf"
    if os.path.exists(light_path):
        try:
            pdfmetrics.registerFont(TTFont('PretendardLight', light_path))
            light_registered = True
        except Exception:
            pass

    # 만약 로컬 TTF 파일 등록 실패 시 백업용 나눔고딕 웹 폰트 로드
    if not (bold_registered and light_registered):
        try:
            font_url = "https://cdn.jsdelivr.net/gh/googlefonts/nanum-gothic@main/fonts/ttf/NanumGothic-Regular.ttf"
            req = urllib.request.Request(font_url, headers={'User-Agent': 'Mozilla/5.0'})
            font_data = urllib.request.urlopen(req).read()
            font_bytes = io.BytesIO(font_data)
            pdfmetrics.registerFont(TTFont('NanumGothic', font_bytes))
        except Exception:
            pass

register_pretendard_fonts()


# ==========================================
# 1. 엑셀 파일 로드 및 데이터 전처리
# ==========================================
@st.cache_data
def load_excel_data():
    try:
        excel_file = "closure_data.xlsx"
        xls = pd.ExcelFile(excel_file, engine="openpyxl")

        df_failures = pd.read_excel(xls, sheet_name="1. 폐업실패요인 데이터", engine="openpyxl")
        df_categories = pd.read_excel(xls, sheet_name="2. 카테고리", engine="openpyxl")
        df_consulting = pd.read_excel(xls, sheet_name="3. 컨설팅 분야", engine="openpyxl")

        df_failures["나이대_표시"] = df_failures["나이대"].astype(str) + "대"
        df_failures["업종"] = df_failures["업종"].fillna("기타")

        return df_failures, df_categories, df_consulting
    except FileNotFoundError:
        st.error("데이터 파일(closure_data.xlsx)을 찾을 수 없습니다. 깃허브 파일명을 확인해 주세요.")
        return None, None, None
    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        return None, None, None


df_failures, df_categories, df_consulting = load_excel_data()

if df_failures is not None:
    data_count_str = f"{len(df_failures):,}건"
else:
    data_count_str = "46,540건"


# ==========================================
# 2. 페이지 기본 설정 및 원래 UI 제목 복원
# ==========================================
st.set_page_config(
    page_title="폐업자 실패요인 데이터 기반 맞춤형 경영진단 리포트",
    layout="wide",
)

st.title("📊 폐업자 실패요인 데이터 기반 맞춤형 경영진단 리포트")
st.caption(
    f"축적된 폐업 소상공인 실패요인 데이터({data_count_str})를 바탕으로 객관적인 경영 위험 분석과 맞춤형 컨설팅을 제안드립니다."
)


def convert_html_to_pdf(html_string):
    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_string, dest=result, encoding="utf-8")
    if pisa_status.err:
        return None
    return result.getvalue()


# ==========================================
# 3. 사용자 입력 폼 (원래 UI 라벨 원복)
# ==========================================
if df_failures is not None:
    st.sidebar.header("📋 상담업체 프로필 선택")

    selected_district = st.sidebar.selectbox(
        "자치구", sorted(df_failures["자치구"].dropna().unique())
    )
    
    user_industry_input = st.sidebar.text_input(
        "업종 검색 및 입력",
        value="한식 음식점",
        help="상담 업체의 세부 업종 키워드를 입력하세요.(예: 한식 음식점, 카페, 디저트카페. 미용실, 의류 도매업 등)",
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

    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.sidebar.text_input("Gemini API Key", type="password")

    generate_btn = st.sidebar.button("🚀 경영진단 리포트 생성하기", use_container_width=True)

    # ==========================================
    # 4. 데이터 필터링 & API 호출
    # ==========================================
    if generate_btn:
        if not api_key:
            st.warning("Gemini API Key가 설정되지 않았습니다. Secrets 또는 사이드바를 확인해 주세요.")
        elif not user_industry_input.strip():
            st.warning("업종 키워드를 입력해 주세요.")
        else:
            clean_industry = user_industry_input.strip()

            industry_mask = df_failures["업종"].str.contains(clean_industry, case=False, na=False)
            
            filtered_failures = df_failures[
                industry_mask
                & (df_failures["자치구"] == selected_district)
                & (df_failures["나이대_표시"] == selected_age_display)
                & (df_failures["성별"] == selected_gender)
            ]

            is_fallback = False
            if filtered_failures.empty:
                filtered_failures = df_failures[industry_mask]
                is_fallback = True

            if filtered_failures.empty:
                filtered_failures = df_failures.head(30)
                matched_industries_str = f"'{clean_industry}' 관련 업종 종합 데이터"
            else:
                matched_industries = filtered_failures["업종"].unique()[:5]
                matched_industries_str = ", ".join(matched_industries)

            swot_summary = ""
            sample_df = filtered_failures.head(20)
            for idx, row in sample_df.iterrows():
                swot_summary += f"- [{row['코드']}] {row['항목']}: {row['내용']} (세부사례: {row['추가내용'] if pd.notna(row['추가내용']) else '없음'})\n"

            consulting_list_text = ""
            for idx, row in df_consulting.iterrows():
                consulting_list_text += (
                    f"- [{row['항목']}] {row['분야']} > {row['세부 분야']}\n"
                )

            prompt = f"""
            당신은 소상공인 지원사업의 경영컨설팅 및 데이터 분석 전문가입니다.
            축적된 실제 소상공인 폐업 조사 데이터베이스({data_count_str})에서 추출된 아래 자료를 바탕으로, 상담 고객을 위한 객관적이고 논리적인 [경영 진단 및 맞춤 컨설팅 추천 리포트]를 작성하세요.

            [상담 고객 프로필]
            - 자치구: {selected_district} | 입력된 업종: {clean_industry} (매칭된 유사 업종: {matched_industries_str}) | 연령대: {selected_age_display} | 성별: {selected_gender}
            {"* 참고: 해당 정밀 조건 데이터 수가 적어 입력 업종의 종합 데이터 경향성을 분석에 반영했습니다." if is_fallback else ""}

            [실제 축적된 동종/유사 업종의 폐업 SWOT 및 실패 요인 사례]
            {swot_summary}

            [자사(기관)에서 제공 중인 실제 컨설팅 지원사업 목록]
            {consulting_list_text}

            [리포트 작성 지시사항]
            1. **동종/유사 업종 폐업 원인 종합 진단**: 제공된 SWOT 실패 요인을 분석하여, '{clean_industry}' 관련 업종의 소상공인들이 주로 겪는 경영 위기 패턴(약점 및 위협요인)을 데이터에 기반하여 설명하세요.
            2. **예상 보완점 및 경영 인사이트**: 단순 자금(보증) 지원만으로는 해결되지 않는 핵심 경영 위험 요인을 지적하고, 우선적으로 개선해야 할 전략적 보완점을 제시하세요.
            3. **★ 맞춤형 컨설팅 지원사업 추천 (가장 중요)**: [자사 제공 컨설팅 지원사업 목록] 중에서 이 업체의 약점과 위협을 극복하는 데 가장 직결되는 컨설팅 분야/세부터겟 2~3개를 명확히 지목하고, 왜 이 컨설팅이 필요한지 논리적 사유를 함께 작성하세요.
            4. **격식 및 톤앤매너**: 소상공인 사장님에게 전달되는 전문 기관의 공식 리포트 어조(~하오니, ~를 권장합니다)로 단정하게 작성하세요. 개인정보는 일절 언급하지 마세요.
            """

            with st.spinner(f"'{clean_industry}' 관련 빅데이터를 분석하여 맞춤 진단서를 생성 중입니다..."):
                try:
                    client = genai.Client(api_key=api_key.strip())
                    
                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt,
                    )
                    
                    report_text = response.text

                    st.success("경영 진단 및 컨설팅 지원사업 매칭 리포트가 생성되었습니다!")

                    st.markdown("---")
                    st.subheader(
                        f"📌 [{selected_district} / {clean_industry} / {selected_age_display} {selected_gender}] 맞춤 경영 진단서"
                    )
                    st.write(report_text)

                    # 💡 Pretendard-Bold (제목) & Pretendard-Light (본문) 폰트 할당 HTML
                    # xhtml2pdf의 폰트 서칭 에러를 막기 위해 font-weight: normal로 제어
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
                        <style>
                            @page {{
                                size: a4 portrait;
                                margin: 2cm;
                            }}
                            body {{
                                font-family: 'PretendardLight', 'NanumGothic', sans-serif;
                                font-weight: normal;
                                line-height: 1.6;
                                color: #333333;
                            }}
                            h1 {{
                                font-family: 'PretendardBold', 'NanumGothic', sans-serif;
                                font-weight: normal;
                                color: #1E3A8A;
                                font-size: 16pt;
                                border-bottom: 2px solid #1E3A8A;
                                padding-bottom: 5px;
                                margin-bottom: 15px;
                            }}
                            .info-box {{
                                font-family: 'PretendardLight', 'NanumGothic', sans-serif;
                                font-weight: normal;
                                background-color: #F3F4F6;
                                border: 1px solid #E5E7EB;
                                padding: 10px;
                                font-size: 9pt;
                                margin-bottom: 15px;
                            }}
                            .content {{
                                font-family: 'PretendardLight', 'NanumGothic', sans-serif;
                                font-weight: normal;
                                font-size: 10pt;
                                white-space: pre-wrap;
                                word-wrap: break-word;
                            }}
                        </style>
                    </head>
                    <body>
                        <h1>소상공인 경영진단 및 맞춤 컨설팅 매칭 리포트</h1>
                        <div class="info-box">
                            <strong>상담 고객 프로필:</strong> {selected_district} | {clean_industry} | {selected_age_display} | {selected_gender}<br/>
                            <strong>분석 기반:</strong> 소상공인 폐업실태 조사 데이터베이스({data_count_str}) 기반 자동 추출<br/>
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
                            file_name=f"Report_{selected_district}_{clean_industry}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )

                except Exception as e:
                    st.error(f"리포트 생성 중 오류가 발생했습니다: {e}")
