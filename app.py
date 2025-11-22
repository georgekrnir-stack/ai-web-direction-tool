import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide")

# タイトル
st.title("🚀 AI Web Direction Assistant")

# サイドバー：APIキー設定
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("Gemini API Key", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        st.success("API Key is set!")
    else:
        st.warning("APIキーを入力してください")

    # リセットボタン
    if st.button("データをリセット"):
        st.session_state.clear()
        st.rerun()

# モデル取得関数（キャッシュして高速化）
@st.cache_resource
def get_model():
    try:
        # モデル選択ロジック（簡易版）
        return genai.GenerativeModel('gemini-1.5-flash')
    except:
        return None

model = get_model()
safety_settings = {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE}

# ==========================================
# 2. 状態管理（Session State）
# ==========================================
# Streamlitでは st.session_state という辞書でデータを保持します
if "confirmed" not in st.session_state:
    st.session_state.confirmed = """【基本情報】
クライアント名: 
業種: 
ターゲット: 

【決定した方針・コンセプト】
・

【仕様・要件（予算・納期など）】
・
"""

if "pending" not in st.session_state:
    st.session_state.pending = """【次回MTGでの確認事項】
・

【解消すべき矛盾・懸念点】
・
"""

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] # 表示用: [{"role": "user", "text": "..."}, ...]

if "chat_context" not in st.session_state:
    st.session_state.chat_context = [] # AI送信用の単純リスト

# ==========================================
# 3. 画面レイアウト
# ==========================================

# 画面を左右に分割
left_col, right_col = st.columns([1, 1])

# --- 左カラム：情報の棚（バイブル） ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    st.markdown("#### ✅ プロジェクト定義書（確定情報）")
    # heightで高さを指定可能
    new_confirmed = st.text_area("確定情報", value=st.session_state.confirmed, height=300, key="input_confirmed", label_visibility="collapsed")
    # 手動編集を反映
    st.session_state.confirmed = new_confirmed

    st.markdown("---")

    st.markdown("#### 🚧 Todo・確認リスト（未定事項）")
    new_pending = st.text_area("未定事項", value=st.session_state.pending, height=200, key="input_pending", label_visibility="collapsed")
    st.session_state.pending = new_pending


# --- 右カラム：AIツールボックス ---
with right_col:
    st.subheader("🛠️ AIツールボックス")
    
    # タブの作成
    tab1, tab2, tab3, tab4 = st.tabs(["📨 事前分析", "🗣️ 会議サポート", "📑 最終出力", "💡 壁打ち"])

    # --- Tab 1: 事前分析 ---
    with tab1:
        st.markdown("**雑多なメモから情報を整理します**")
        tool_a_input = st.text_area("メモを入力", height=100)
        
        if st.button("分析実行", key="btn_a"):
            if not api_key:
                st.error("APIキーを入れてください")
            else:
                with st.spinner("AIが分析中..."):
                    prompt = f"""
                    あなたはWebディレクターです。メモを分析し2つに分けてください。
                    【セクション1: 基本情報】確定的な事実。
                    【セクション2: 戦略・質問リスト】確認・提案すべきこと。
                    入力メモ: {tool_a_input}
                    出力形式: ===SECTION1=== (内容) ===SECTION2=== (内容)
                    """
                    try:
                        res = model.generate_content(prompt, safety_settings=safety_settings)
                        text = res.text
                        if "===SECTION2===" in text:
                            parts = text.split("===SECTION2===")
                            st.session_state.confirmed = parts[0].replace("===SECTION1===", "").strip()
                            st.session_state.pending = parts[1].strip()
                        else:
                            st.session_state.confirmed = text
                        
                        st.success("左側のバイブルに反映しました！")
                        st.rerun() # 画面をリロードして反映を表示
                    except Exception as e:
                        st.error(f"エラー: {e}")

    # --- Tab 2: 会議サポート ---
    with tab2:
        st.markdown("**会議ログから情報の更新・仕分けを行います**")
        tool_b_input = st.text_area("会議ログ", height=150)
        tool_b_mode = st.selectbox("モード", ["ヒアリング漏れチェック", "議事録・合意形成"])
        
        # AIの回答を一時保存する場所（ボタンを押しても消えないように）
        if "tool_b_result_conf" not in st.session_state:
            st.session_state.tool_b_result_conf = ""
        if "tool_b_result_pend" not in st.session_state:
            st.session_state.tool_b_result_pend = ""

        if st.button("AI実行（分析）", key="btn_b"):
            if not api_key:
                st.error("APIキーを入れてください")
            else:
                with st.spinner("分析中..."):
                    instruction = "会議ログから「新たに判明した事実」を確定情報に追記し、Todoリストを更新してください。" if tool_b_mode == 'ヒアリング漏れチェック' else "会議ログから合意事項を抽出し、確定情報を更新してください。"
                    prompt = f"""
                    【現在のプロジェクト定義書】{st.session_state.confirmed}
                    【現在のTodoリスト】{st.session_state.pending}
                    【会議ログ】{tool_b_input}
                    【指示】{instruction}
                    ルール: 1.両リストを最新化。 2.追加箇所に「★」付与。 3.出力形式: ===CONFIRMED=== (内容) ===PENDING=== (内容)
                    """
                    try:
                        res = model.generate_content(prompt, safety_settings=safety_settings)
                        text = res.text
                        if "===PENDING===" in text:
                            parts = text.split("===PENDING===")
                            st.session_state.tool_b_result_conf = parts[0].replace("===CONFIRMED===", "").strip()
                            st.session_state.tool_b_result_pend = parts[1].strip()
                        else:
                            st.session_state.tool_b_result_conf = text
                    except Exception as e:
                        st.error(f"エラー: {e}")

        # 結果表示と反映ボタン
        if st.session_state.tool_b_result_conf:
            st.markdown("👇 **AI更新案（確認して反映してください）**")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.info("確定情報の更新案")
                st.text_area("Conf", value=st.session_state.tool_b_result_conf, height=200, key="disp_conf", disabled=True)
            with col_b2:
                st.warning("Todoの更新案")
                st.text_area("Pend", value=st.session_state.tool_b_result_pend, height=200, key="disp_pend", disabled=True)
            
            if st.button("↑ ★を消して左側に反映する", type="primary"):
                st.session_state.confirmed = st.session_state.tool_b_result_conf.replace("★", "")
                st.session_state.pending = st.session_state.tool_b_result_pend
                st.session_state.tool_b_result_conf = "" # 結果をクリア
                st.session_state.tool_b_result_pend = ""
                st.success("反映しました！")
                st.rerun()

    # --- Tab 3: 最終出力 ---
    with tab3:
        st.markdown("**確定情報のみから指示書を作成します**")
        if st.button("制作指示書を出力", type="primary", key="btn_c"):
             with st.spinner("作成中..."):
                prompt = f"""
                あなたはシニアディレクターです。以下の「確定情報」のみを基に、デザイナーへの制作指示書を作成してください。
                【プロジェクト定義書】{st.session_state.confirmed}
                """
                try:
                    res = model.generate_content(prompt, safety_settings=safety_settings)
                    st.markdown(res.text)
                except Exception as e:
                    st.error(f"エラー: {e}")

    # --- Tab 4: 壁打ちチャット ---
    with tab4:
        st.markdown("**プロジェクト情報を踏まえた相談チャット**")
        
        # チャット履歴の表示
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["text"])

        # 入力エリア
        user_input = st.chat_input("質問を入力...")
        if user_input:
            # ユーザーの入力を表示・保存
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_input)
            st.session_state.chat_history.append({"role": "user", "text": user_input})
            
            # AI用履歴の作成
            st.session_state.chat_context.append(f"User: {user_input}")
            history_text = "\n".join(st.session_state.chat_context[-10:]) # 直近10件

            # プロンプト作成
            prompt = f"""
            あなたはWeb制作プロジェクトの専属アドバイザーです。
            【現在のプロジェクト定義書（確定）】{st.session_state.confirmed}
            【現在のTodo・未定事項】{st.session_state.pending}
            【これまでのチャット履歴】{history_text}
            ---
            User: {user_input}
            """
            
            # 回答生成
            try:
                response = model.generate_content(prompt, safety_settings=safety_settings)
                ai_resp = response.text
                
                # AIの回答を表示・保存
                with chat_container:
                    with st.chat_message("assistant"):
                        st.markdown(ai_resp)
                st.session_state.chat_history.append({"role": "assistant", "text": ai_resp})
                st.session_state.chat_context.append(f"AI: {ai_resp}")
            
            except Exception as e:
                st.error(f"エラー: {e}")