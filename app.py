import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide")
st.title("🚀 AI Web Direction Assistant (v6.1)")

# --- 接続診断機能 ---
def try_get_valid_model(api_key):
    """使えるモデルを総当たりで探す関数"""
    genai.configure(api_key=api_key)
    
    # 1. まずリスト取得を試みる
    try:
        models = genai.list_models()
        available_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
    except:
        available_names = []

    # 2. 優先順位リスト（上から順に試す）
    priority_candidates = [
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-1.5-flash-001',
        'gemini-1.5-pro-001',
        'models/gemini-1.5-flash', 
        'models/gemini-1.5-pro',
        'gemini-pro'
    ]

    # リストが取れた場合はそこからマッチング
    if available_names:
        for candidate in priority_candidates:
            # "gemini-1.5-flash" が "models/gemini-1.5-flash-001" に含まれるか確認
            match = next((m for m in available_names if candidate in m), None)
            if match:
                return match
    
    # リストが取れない、またはマッチしない場合は、エイリアスを信じてデフォルトを返す
    return 'gemini-1.5-flash'

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("Gemini API Key", type="password")
    
    active_model = None
    
    if api_key:
        # 接続テスト
        try:
            model_name = try_get_valid_model(api_key)
            active_model = genai.GenerativeModel(model_name)
            st.success(f"✅ 接続成功\n\nモデル: `{model_name}`")
        except Exception as e:
            st.error(f"❌ 接続エラー: {e}")
    else:
        st.warning("APIキーを入力してください")

    if st.button("データをリセット"):
        st.session_state.clear()
        st.rerun()

safety_settings = {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE}

# ==========================================
# 2. 状態管理
# ==========================================
if "confirmed" not in st.session_state:
    st.session_state.confirmed = """【基本情報】
クライアント名: 
業種: 
ターゲット: 

【決定した方針】
・

【要件（予算・納期）】
・
"""
if "pending" not in st.session_state:
    st.session_state.pending = """【次回確認事項】
・
"""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "chat_context" not in st.session_state:
    st.session_state.chat_context = [] 

# ==========================================
# 3. 画面レイアウト
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左カラム ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    st.caption("確定した情報はここに蓄積されます")
    new_confirmed = st.text_area("確定情報", value=st.session_state.confirmed, height=300, label_visibility="collapsed")
    st.session_state.confirmed = new_confirmed
    st.markdown("---")
    st.caption("未定・宿題リスト")
    new_pending = st.text_area("未定事項", value=st.session_state.pending, height=200, label_visibility="collapsed")
    st.session_state.pending = new_pending

# --- 右カラム ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📨 事前分析", "🗣️ 会議サポート", "📑 最終出力", "💡 壁打ち"])

    # --- Tab 1 ---
    with tab1:
        st.write("メモから情報を整理します")
        tool_a_input = st.text_area("メモを入力", height=100)
        if st.button("分析実行", key="btn_a"):
            if not active_model:
                st.error("APIキー設定を確認してください")
            else:
                with st.spinner("分析中..."):
                    try:
                        prompt = f"あなたはWebディレクターです。以下のメモを【基本情報】と【戦略・質問リスト】に分けて整理してください。\nメモ: {tool_a_input}\n出力形式: ===SECTION1=== (基本情報) ===SECTION2=== (戦略)"
                        res = active_model.generate_content(prompt, safety_settings=safety_settings)
                        
                        if "===SECTION2===" in res.text:
                            parts = res.text.split("===SECTION2===")
                            st.session_state.confirmed = parts[0].replace("===SECTION1===", "").strip()
                            st.session_state.pending = parts[1].strip()
                        else:
                            st.session_state.confirmed = res.text
                        
                        st.success("左側のパネルに反映しました！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")

    # --- Tab 2 ---
    with tab2:
        st.write("会議ログから情報を更新します")
        tool_b_input = st.text_area("会議ログ", height=150)
        tool_b_mode = st.selectbox("モード", ["ヒアリング漏れチェック", "議事録・合意形成"])
        
        if "tool_b_result_conf" not in st.session_state:
            st.session_state.tool_b_result_conf = ""
            st.session_state.tool_b_result_pend = ""

        if st.button("AI実行", key="btn_b"):
            if not active_model:
                st.error("APIキー設定を確認してください")
            else:
                with st.spinner("分析中..."):
                    try:
                        instruction = "未定事項を更新してください" if tool_b_mode == 'ヒアリング漏れチェック' else "合意事項を抽出してください"
                        prompt = f"【確定情報】{st.session_state.confirmed}\n【未定情報】{st.session_state.pending}\n【ログ】{tool_b_input}\n指示:{instruction}\nルール:確定情報の追記箇所に★をつけること。\n出力形式: ===CONFIRMED=== (内容) ===PENDING=== (内容)"
                        
                        res = active_model.generate_content(prompt, safety_settings=safety_settings)
                        if "===PENDING===" in res.text:
                            parts = res.text.split("===PENDING===")
                            st.session_state.tool_b_result_conf = parts[0].replace("===CONFIRMED===", "").strip()
                            st.session_state.tool_b_result_pend = parts[1].strip()
                        else:
                            st.session_state.tool_b_result_conf = res.text
                    except Exception as e:
                        st.error(f"エラー: {e}")

        if st.session_state.tool_b_result_conf:
            st.info("▼ 更新案（確認して反映ボタンを押してください）")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.text_area("確定情報の更新案", value=st.session_state.tool_b_result_conf, height=200, disabled=True)
            with col_b2:
                st.text_area("Todoの更新案", value=st.session_state.tool_b_result_pend, height=200, disabled=True)
            
            if st.button("↑ 反映する", type="primary"):
                st.session_state.confirmed = st.session_state.tool_b_result_conf.replace("★", "")
                st.session_state.pending = st.session_state.tool_b_result_pend
                st.session_state.tool_b_result_conf = ""
                st.session_state.tool_b_result_pend = ""
                st.success("反映完了")
                st.rerun()

    # --- Tab 3 ---
    with tab3:
        if st.button("指示書を出力", type="primary"):
             if not active_model:
                st.error("APIキー設定を確認してください")
             else:
                with st.spinner("作成中..."):
                    try:
                        prompt = f"あなたはシニアディレクターです。以下の情報から制作指示書を作成してください。\n{st.session_state.confirmed}"
                        res = active_model.generate_content(prompt, safety_settings=safety_settings)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"エラー: {e}")

    # --- Tab 4 (壁打ち) ---
    with tab4:
        st.write("フリー相談チャット")
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["text"])

        if user_input := st.chat_input("質問を入力..."):
            if not active_model:
                st.error("APIキー設定を確認してください")
            else:
                st.session_state.chat_history.append({"role": "user", "text": user_input})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(user_input)
                
                st.session_state.chat_context.append(f"User: {user_input}")
                history_text = "\n".join(st.session_state.chat_context[-5:])

                try:
                    prompt = f"あなたはWeb制作のアドバイザーです。\n【プロジェクト状況】{st.session_state.confirmed}\n【未定事項】{st.session_state.pending}\n【履歴】{history_text}\nユーザー: {user_input}"
                    
                    # ストリーミングなしで一括生成（エラー特定のため）
                    res = active_model.generate_content(prompt, safety_settings=safety_settings)
                    ai_resp = res.text
                    
                    st.session_state.chat_history.append({"role": "assistant", "text": ai_resp})
                    st.session_state.chat_context.append(f"AI: {ai_resp}")
                    
                    with chat_container:
                        with st.chat_message("assistant"):
                            st.markdown(ai_resp)
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
