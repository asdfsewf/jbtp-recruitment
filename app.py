import streamlit as st
import pandas as pd
import re
import os
import google.generativeai as genai

# ==========================================
# 0. 초기 설정 및 시스템 기억력(Session) 세팅
# ==========================================
st.set_page_config(page_title="JBTP 스마트 채용 시스템", layout="wide", page_icon="🏢")

genai.configure(api_key="AQ.Ab8RN6LRiK2sRPiytWEfRQ1ckWj6WebH-6mV2dY7lvLMb1-TaA")
model = genai.GenerativeModel('gemini-2.5-flash')

FAIL_DIR = "./2026_상반기_과장채용_불합격자_서류"
os.makedirs(FAIL_DIR, exist_ok=True)

if "cv_data" not in st.session_state: st.session_state.cv_data = None
if "written_pass_data" not in st.session_state: st.session_state.written_pass_data = None
if "doc_pass_data" not in st.session_state: st.session_state.doc_pass_data = None
if "doc_eval" not in st.session_state: st.session_state.doc_eval = {}
if "masked_status" not in st.session_state: st.session_state.masked_status = {}
if "step1_df" not in st.session_state: st.session_state.step1_df = None
if "step2_df" not in st.session_state: st.session_state.step2_df = None
if "step3_df" not in st.session_state: st.session_state.step3_df = None
if "step4_df" not in st.session_state: st.session_state.step4_df = None
if "ai_summaries" not in st.session_state: st.session_state.ai_summaries = {}

st.title("🤖 (재)전북테크노파크 순차형 채용 관리 시스템")
st.markdown("---")

st.sidebar.header("⚙️ 채용 진행 단계")
step = st.sidebar.radio("현재 진행 중인 전형을 선택하세요:", 
    ["1단계: 지원서 접수 (기본 적격성)", 
     "2단계: 필기전형 (점수 매칭)", 
     "3단계: 서류전형 (AI & 블라인드)", 
     "4단계: 면접전형 (최종 선발)"])

# 가산점 로직: 필기(300점 만점)와 면접(고정 점수) 구분
def calculate_bonus(max_score, text):
    text = str(text)
    # 필기 가산점(비율 계산)
    if max_score == 300:
        if any(k in text for k in ['1호', '2호', '4호', '순직군경']): return max_score * 0.10
        elif any(k in text for k in ['3호', '5호', '장애']): return max_score * 0.05
    # 면접 가산점(고정 점수: 10점/5점)
    elif max_score == 100:
        if any(k in text for k in ['1호', '2호', '4호', '순직군경']): return 10
        elif any(k in text for k in ['3호', '5호', '장애']): return 5
    return 0

def extract_certificates(row):
    certs = ['전산회계', '세무회계', '재경관리사', '컴퓨터활용능력']
    combined_text = str(row.get('자격사항', '')) + str(row.get('우대사항', ''))
    found = [c for c in certs if c in combined_text]
    return ", ".join(found) if found else "보유 자격증 없음"

def clean_columns(df):
    df.columns = [c.strip() for c in df.columns]
    rename_map = {
        'ncs공통': 'NCS공통', '전공': '전공', '지원번호': '지원번호',
        '경력사항': '경력사항', '우대사항': '우대사항', '가점유형': '가점유형',
        '실무면접': '실무면접', '종합면접': '종합면접', '인성검사': '인성검사', '자격사항': '자격사항'
    }
    df = df.rename(columns={c: rename_map.get(c.lower(), c) for c in df.columns})
    return df

# ==========================================
# 1단계: 접수
# ==========================================
if step == "1단계: 지원서 접수 (기본 적격성)":
    st.header("📋 1단계: 지원서 업로드 및 기본 적격성 검증")
    cv_file = st.file_uploader("📂 [지원서 데이터] CSV 업로드", type=['csv'])
    if cv_file:
        df_cv = clean_columns(pd.read_csv(cv_file))
        df_cv['보유자격증'] = df_cv.apply(extract_certificates, axis=1) 
        df_cv['총_경력_개월수'] = df_cv['경력사항'].apply(lambda x: sum(int(y) for y in re.findall(r'(\d+)\s*년', str(x))) * 12 + sum(int(m) for m in re.findall(r'(\d+)\s*개월', str(x))))
        df_cv['서류결과'] = df_cv['총_경력_개월수'].apply(lambda x: "✅ 접수 완료" if x >= 60 else "❌ 경력 미달")
        st.session_state.step1_df = df_cv
    if st.session_state.step1_df is not None:
        st.dataframe(st.session_state.step1_df[['지원번호', '경력사항', '보유자격증', '우대사항', '서류결과']])
        if st.button("🔒 [지원서 접수 마감] 적격자 넘기기"): 
            st.session_state.cv_data = st.session_state.step1_df[st.session_state.step1_df['서류결과'] == "✅ 접수 완료"]

# ==========================================
# 2단계: 필기
# ==========================================
elif step == "2단계: 필기전형 (점수 매칭)":
    st.header("📝 2단계: 필기 점수 업로드 및 5배수 선발")
    score_file = st.file_uploader("📂 [필기 점수 데이터] CSV 업로드", type=['csv'])
    if score_file and st.session_state.cv_data is not None:
        df_m = pd.merge(st.session_state.cv_data, clean_columns(pd.read_csv(score_file)), on='지원번호')
        df_m['필기가산점'] = df_m['우대사항'].apply(lambda x: calculate_bonus(300, x))
        df_m['필기총점'] = df_m['NCS공통'] + df_m['전공'] + df_m['필기가산점']
        df_m['필기결과'] = df_m['필기총점'].apply(lambda x: "🟢 필기 합격" if x > 120 else "🔴 탈락")
        st.session_state.step2_df = df_m
    if st.session_state.step2_df is not None:
        st.dataframe(st.session_state.step2_df[['지원번호', 'NCS공통', '전공', '필기가산점', '필기총점', '필기결과']])
        if st.button("🔒 [필기전형 마감] 합격자 저장"): st.session_state.written_pass_data = st.session_state.step2_df[st.session_state.step2_df['필기결과'] == "🟢 필기 합격"]

# ==========================================
# 3단계: 서류 (블라인드, AI 요약, 인성검사)
# ==========================================
elif step == "3단계: 서류전형 (AI & 블라인드)":
    st.header("🔍 3단계: 서류전형")
    if st.session_state.written_pass_data is not None:
        df_w = st.session_state.written_pass_data
        app_ids = [f"지원번호 {r['지원번호']} [{r.get('보유자격증', '없음')}]" for _, r in df_w.iterrows()]
        sel_id_str = st.selectbox("평가할 지원자", app_ids).split(" ")[1]
        sel_row = df_w[df_w['지원번호'].astype(str) == sel_id_str].iloc[0]
        
      # 1. 지원자 기본 정보
       # 1. 지원자 상세 프로필 및 경험/경력사항 (CSS 강화 버전)
        st.markdown("### 👤 지원자 상세 프로필")
        col1, col2, col3 = st.columns(3)
        col1.metric("학력사항", str(sel_row.get('학력사항', 'x')) if str(sel_row.get('학력사항', '')) != 'nan' else 'x')
        col2.metric("전공명", str(sel_row.get('전공명', 'x')) if str(sel_row.get('전공명', '')) != 'nan' else 'x')
        col3.metric("취업지원 대상자", "대상자" if calculate_bonus(1, sel_row.get('우대사항', '')) > 0 else "비대상")
        
        col4, col5 = st.columns(2)
        col4.metric("자격사항", str(sel_row.get('자격사항', 'x')) if str(sel_row.get('자격사항', '')) != 'nan' else 'x')

        # 강력한 CSS 적용
        st.markdown("""
            <style>
            /* 라벨 크기 키우기 및 흰색 적용 */
            .big-font { 
                font-size: 24px !important; 
                font-weight: bold !important; 
                color: white !important; 
            }
            /* text_area 내부 글씨 크기 및 색상 설정 */
            .stTextArea textarea { 
                font-size: 18px !important; 
                line-height: 1.5 !important; 
                color: #ffffff !important; 
                background-color: #333333 !important; 
            }
            </style>
        """, unsafe_allow_html=True)
        
        # 경험사항
        exp_text = str(sel_row.get('경험사항', 'x'))
        if exp_text.lower() == 'nan': exp_text = 'x'
        st.markdown("<p class='big-font'>경험사항</p>", unsafe_allow_html=True)
        st.text_area(label="", value=exp_text, height=100, disabled=True, key="exp_area_v3")
        
        # 경력사항
        career_text = str(sel_row.get('경력사항', 'x'))
        if career_text.lower() == 'nan': career_text = 'x'
        st.markdown("<p class='big-font'>경력사항</p>", unsafe_allow_html=True)
        st.text_area(label="", value=career_text, height=150, disabled=True, key="career_area_v3")
        
        st.markdown("---")
        
        # 2. 자기소개서 요약 및 원본
        st.markdown("### 📝 자기소개서 요약 및 원본")
        if st.button("AI 자소서 요약"):
            for i in [1, 2, 3]:
                # 컬럼명이 정확하지 않을 수 있으므로 get으로 안전하게 가져옴
                col_name = f'자기소개서 {i}'
                val = sel_row.get(col_name)
                if pd.notna(val):
                    try: st.session_state.ai_summaries[f"{sel_id_str}_{i}"] = model.generate_content(f"요약해:\n{val}").text
                    except: st.error(f"AI 요약 실패 (API 제한)")
        
        for i in [1, 2, 3]:
            if f"{sel_id_str}_{i}" in st.session_state.ai_summaries:
                st.success(f"🤖 AI 요약 {i}: {st.session_state.ai_summaries[f'{sel_id_str}_{i}']}")
                st.caption(f"원문 {i}: {sel_row.get(f'자기소개서 {i}', '')}")

        st.markdown("---")

        # 3. 서류 평가 결과
        def update_eval(): st.session_state.doc_eval[sel_id_str] = st.session_state[f"ev_{sel_id_str}"]
        st.radio("서류 평가 결과", ["미평가", "합격", "불합격"], key=f"ev_{sel_id_str}", index=["미평가", "합격", "불합격"].index(st.session_state.doc_eval.get(sel_id_str, "미평가")), horizontal=True, on_change=update_eval)
        
        st.markdown("---")

        # 4. 인사 담당자 평가 현황 (인성검사 업로드 전에도 확인 가능)
        st.write("##### 📊 인사 담당자 평가 현황")
        df_status = df_w[['지원번호']].copy()
        df_status['상태'] = df_status['지원번호'].astype(str).map(st.session_state.doc_eval).fillna("미평가")
        st.dataframe(df_status)
        
        # 5. 인성검사 CSV 업로드
        pers_file = st.file_uploader("📂 인성검사 CSV 업로드", type=['csv'])
        if pers_file:
            df_p = clean_columns(pd.read_csv(pers_file))
            df_res = pd.merge(df_w[df_w['지원번호'].astype(str).map(st.session_state.doc_eval) == '합격'], df_p, on='지원번호')
            df_res['인성_결과'] = df_res['인성검사'].apply(lambda x: "❌ 탈락" if str(x).lower() in ['x', '미참여', '결시', 'none', 'nan'] else "✅ 통과")
            st.session_state.step3_df = df_res
            st.dataframe(df_res[['지원번호', '인성검사', '인성_결과']])
            if st.button("최종 면접 대상자 확정"): st.session_state.doc_pass_data = df_res[df_res['인성_결과'] == "✅ 통과"]
# ==========================================
# 4단계: 면접 (버튼 강제 실행 방식)
# ==========================================
elif step == "4단계: 면접전형 (최종 선발)":
    st.header("🏆 4단계: 면접전형")
    
    TARGET_COUNT = 1 
    
    if st.session_state.doc_pass_data is not None:
        int_file = st.file_uploader("📂 면접 점수 CSV 업로드", type=['csv'])
        
        # 버튼을 눌러야만 로직이 작동하게 변경
        if int_file and st.button("면접 결과 계산하기"):
            df_int = clean_columns(pd.read_csv(int_file))
            
            if '실무면접' in df_int.columns and '종합면접' in df_int.columns:
                df_f = pd.merge(st.session_state.doc_pass_data, df_int, on='지원번호')
                
                # 가산점 및 점수 계산
                df_f['면접가산점'] = df_f['우대사항'].apply(lambda x: calculate_bonus(100, x))
                df_f['최종점수'] = df_f['실무면접'] + df_f['종합면접'] + df_f['면접가산점']
                
                # 정렬 및 판정
                df_f = df_f.sort_values(by='최종점수', ascending=False).reset_index(drop=True)
                
                def determine_pass(idx, score):
                    if score < 70: return "🔴 불합격"
                    if idx < TARGET_COUNT: return "🏆 최종 합격"
                    elif idx < TARGET_COUNT * 3: return "🥈 예비 합격"
                    else: return "🔴 불합격"

                df_f['판정'] = [determine_pass(i, row['최종점수']) for i, row in df_f.iterrows()]
                st.session_state.step4_df = df_f
                
                # 결과 출력
                st.write(f"### [계산 완료] 결과 확인")
                st.dataframe(df_f[['지원번호', '최종점수', '우대사항', '판정']])
            else:
                st.error("🚨 '실무면접', '종합면접' 컬럼이 파일에 없습니다!")
        
        # 이미 계산된 결과가 있으면 항상 보여줌
        elif st.session_state.step4_df is not None:
            st.dataframe(st.session_state.step4_df[['지원번호', '최종점수', '우대사항', '판정']])
            
