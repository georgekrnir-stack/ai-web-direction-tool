import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide")
st.title("🚀 AI Web Direction Assistant (v6.2)")

# --- 接続診断機能 ---
def try_get_valid_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = genai.list_models()
        available_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
    except:
        available_names = []

    priority_candidates = [
        'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.5-flash-001',
        'gemini-1.5-pro-001', 'models/gemini-1.5-flash', 
        'models/gemini-1.5-pro', 'gemini-pro'
    ]

    if available_names:
        for candidate in priority_candidates:
            match = next((m for m in available_names if candidate in m), None)
            if match: return match
    return 'gemini-1.5-flash'

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("Gemini API Key", type="password")
    
    active_model = None
    if api_key:
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
    st.session_state.confirmed = """### 【基本情報】
- **クライアント名**: 
- **業種**: 
- **ターゲット**: 

### 【決定した方針】
- 

### 【要件（予算・納期）】
- 
"""
if "pending" not in st.session_state:
    st.session_state.pending = """### 【次回確認事項】
- 
"""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "chat_context" not in st.session_state:
    st.session_state.chat_context = [] 

# ==========================================
# 3. 画面レイアウト
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左カラム：プロジェクト・バイブル（タブ化） ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    st.caption("▼ プロジェクト定義書（確定情報）")
    # タブで「見る」と「書く」を切り替え
    tab_conf_view, tab_conf_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    
    with tab_conf_edit:
        new_confirmed = st.text_area("確定情報エディタ", value=st.session_state.confirmed, height=300, key="input_confirmed", label_visibility="collapsed")
        st.session_state.confirmed = new_confirmed
    with tab_conf_view:
        st.markdown(st.session_state.confirmed) # ここでリッチに表示

    st.markdown("---")

    st.caption("▼ Todo・未定リスト")
    tab_pend_view, tab_pend_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    
    with tab_pend_edit:
        new_pending = st.text_area("未定事項エディタ", value=st.session_state.pending, height=200, key="input_pending", label_visibility="collapsed")
        st.session_state.pending = new_pending
    with tab_pend_view:
        st.markdown(st.session_state.pending)


# --- 右カラム：AIツール ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📨 事前分析", "🗣️ 会議サポート", "📑 最終出力", "💡 壁打ち"])

    # --- Tab 1: 事前分析 ---
    with tab1:
        st.write("メモから情報を整理します")
        tool_a_input = st.text_area("メモを入力", height=100)
        if st.button("分析実行", key="btn_a"):
            if not active_model:
                st.error("APIキー設定を確認してください")
            else:
                with st.spinner("分析中..."):
                    try:
                        # AIにMarkdown記法を使うように指示を強化
                        prompt = f"""
                        あなたはWebディレクターです。以下のメモを【基本情報】と【戦略・質問リスト】に分けて整理してください。
                        見出しには `###` 、重要な箇所には `**太字**` を使い、箇条書き `- ` で読みやすく整形してください。
                        メモ: {tool_a_input}
                        出力形式: ===SECTION1=== (基本情報) ===SECTION2=== (戦略)
                        """
                        res = active_model.generate_content(prompt, safety_settings=safety_settings)
                        
                        if "===SECTION2===" in res.text:
                            parts = res.text.split("===SECTION2===")
                            st.session_state.confirmed = parts[0].replace("===SECTION1===", "").strip()
                            st.session_state.pending = parts[1].strip()
                        else:
                            st.session_state.confirmed = res.text
                        
                        st.success("反映しました！左側のプレビュータブを確認してください。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")

    # --- Tab 2: 会議サポート ---
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
                        # Markdownで見やすくする指示を追加
                        prompt = f"""
                        【確定情報】{st.session_state.confirmed}
                        【未定情報】{st.session_state.pending}
                        【ログ】{tool_b_input}
                        指示:{instruction}
                        ルール:
                        1. 確定情報の追記箇所には `★` をつけ、その行を `**太字**` にしてください。
                        2. 見出しや箇条書きを使い、Markdown形式で読みやすく整理してください。
                        出力形式: ===CONFIRMED=== (内容) ===PENDING=== (内容)
                        """
                        
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
            st.info("▼ 更新案（プレビューで確認できます）")
            
            # ここもタブ化して見やすくする
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                st.caption("確定情報の更新案")
                sub_tab_view1, sub_tab_edit1 = st.tabs(["👀 プレビュー", "✏️ コード"])
                with sub_tab_view1:
                    st.markdown(st.session_state.tool_b_result_conf)
                with sub_tab_edit1:
                    st.text_area("", value=st.session_state.tool_b_result_conf, height=200, disabled=True, label_visibility="collapsed")
            
            with col_b2:
                st.caption("Todoの更新案")
                sub_tab_view2, sub_tab_edit2 = st.tabs(["👀 プレビュー", "✏️ コード"])
                with sub_tab_view2:
                    st.markdown(st.session_state.tool_b_result_pend)
                with sub_tab_edit2:
                    st.text_area("", value=st.session_state.tool_b_result_pend, height=200, disabled=True, label_visibility="collapsed")
            
            if st.button("↑ 反映する", type="primary"):
                # ★マークなどを消去して反映
                clean_conf = st.session_state.tool_b_result_conf.replace("★", "").replace("**★", "**")
                st.session_state.confirmed = clean_conf
                st.session_state.pending = st.session_state.tool_b_result_pend
                
                st.session_state.tool_b_result_conf = ""
                st.session_state.tool_b_result_pend = ""
                st.success("反映完了！")
                st.rerun()

    # --- Tab 3 ---
    with tab3:
        if st.button("指示書を出力", type="primary"):
             if not active_model:
                st.error("APIキー設定を確認してください")
             else:
                with st.spinner("作成中..."):
                    try:
                        prompt = f"あなたはシニアディレクターです。以下の情報から制作指示書を作成してください。Markdownで見やすく整形してください。\n{st.session_state.confirmed}"
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
                    st.markdown(msg["text"]) # ここは元々Markdown対応

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
                    res = active_model.generate_content(prompt, safety_settings=safety_settings)
                    ai_resp = res.text
                    
                    st.session_state.chat_history.append({"role": "assistant", "text": ai_resp})
                    st.session_state.chat_context.append(f"AI: {ai_resp}")
                    
                    with chat_container:
                        with st.chat_message("assistant"):
                            st.markdown(ai_resp)
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
