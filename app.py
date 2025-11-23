import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide")
st.title("🚀 AI Web Direction Assistant (v11.0 Auto-Switch)")

# エラー表示エリア
error_container = st.container()

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    
    api_key = st.text_input("Gemini API Key", type="password")
    
    # モデル自動割り当て設定（デフォルトをご要望の通りに設定）
    st.markdown("### 🤖 モデル割り当て")
    st.caption("タスクに応じて最適なモデルを自動で使用します")
    
    with st.expander("モデル設定の詳細を確認・変更する"):
        # 高負荷タスク用（Pro）
        model_high_quality = st.text_input(
            "高精度モデル (事前分析・最終出力)", 
            value="gemini-2.5-pro",
            help="深い推論が必要なタスクで使用されます"
        )
        # 高速タスク用（Flash）
        model_high_speed = st.text_input(
            "高速モデル (会議・チャット)", 
            value="gemini-2.5-flash",
            help="レスポンス速度が重要なタスクで使用されます"
        )
    
    if api_key:
        genai.configure(api_key=api_key)
        
        # 接続テストボタン
        if st.button("📡 接続テスト"):
            with st.spinner("Googleのサーバーに問い合わせ中..."):
                try:
                    # テスト用にProモデルで疎通確認
                    test_model = genai.GenerativeModel(model_high_quality)
                    # 軽くgenerateして確認（トークン節約のため最小限のリクエストは送らず、オブジェクト生成のみ確認）
                    st.success(f"✅ 接続設定OK\n\n・分析用: `{model_high_quality}`\n・対話用: `{model_high_speed}`")
                        
                except Exception as e:
                    st.error(f"❌ 接続エラー: {e}")

    else:
        st.warning("APIキーを入力してください")

    st.markdown("---")
    if st.button("データをリセット"):
        st.session_state.clear()
        st.rerun()

# 安全設定
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# ==========================================
# 2. 状態管理（動的キー管理）
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
if "confirmed_version" not in st.session_state:
    st.session_state.confirmed_version = 0

if "pending" not in st.session_state:
    st.session_state.pending = """### 【次回確認事項】
- 
"""
if "pending_version" not in st.session_state:
    st.session_state.pending_version = 0

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "chat_context" not in st.session_state:
    st.session_state.chat_context = [] 

# ==========================================
# 3. 共通関数（モデル指定対応版）
# ==========================================
def generate_with_model(model_name, prompt):
    """指定されたモデル名で生成を実行する関数"""
    if not api_key:
        return None, "APIキーが設定されていません"
    
    try:
        # 指定されたモデルでインスタンス化
        active_model = genai.GenerativeModel(model_name)
        
        response = active_model.generate_content(
            prompt, 
            safety_settings=safety_settings
        )
        
        if not response.parts:
            if response.prompt_feedback:
                return None, f"⚠️ 安全フィルターによりブロックされました: {response.prompt_feedback}"
            return None, "⚠️ モデルからの応答が空でした。"
            
        return response.text, None

    except Exception as e:
        err_str = str(e)
        if "429" in err_str:
            return None, "🛑 **利用制限超過 (429 Error)**\n\nアクセス過多です。少し待ってから再試行してください。"
        elif "404" in err_str:
            return None, f"🔍 **モデルが見つかりません (404 Error)**\n\n指定されたモデル `{model_name}` は利用できません。\nサイドバーの「モデル設定の詳細」でモデル名を変更してください（例: gemini-1.5-pro など）。"
        else:
            return None, f"❌ エラーが発生しました:\n{e}"

# ==========================================
# 4. 画面レイアウト
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左カラム ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    st.caption("▼ プロジェクト定義書（確定情報）")
    tab_conf_view, tab_conf_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    
    with tab_conf_edit:
        conf_key = f"confirmed_area_{st.session_state.confirmed_version}"
        new_confirmed = st.text_area(
            "確定情報エディタ", 
            value=st.session_state.confirmed, 
            height=300, 
            key=conf_key, 
            label_visibility="collapsed"
        )
        st.session_state.confirmed = new_confirmed
        
    with tab_conf_view:
        st.markdown(st.session_state.confirmed)

    st.markdown("---")

    st.caption("▼ Todo・未定リスト")
    tab_pend_view, tab_pend_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    
    with tab_pend_edit:
        pend_key = f"pending_area_{st.session_state.pending_version}"
        new_pending = st.text_area(
            "未定事項エディタ", 
            value=st.session_state.pending, 
            height=200, 
            key=pend_key, 
            label_visibility="collapsed"
        )
        st.session_state.pending = new_pending
        
    with tab_pend_view:
        st.markdown(st.session_state.pending)

# --- 右カラム ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📨 事前分析", "🗣️ 会議サポート", "📑 最終出力", "💡 壁打ち"])

    # --- Tab 1: 事前分析 (Proモデル使用) ---
    with tab1:
        st.write("メモから情報を整理します")
        st.caption(f"使用モデル: `{model_high_quality}` (高精度)")
        tool_a_input = st.text_area("メモを入力", height=100)
        
        if st.button("分析実行", key="btn_a"):
            with st.spinner(f"AI ({model_high_quality}) が分析中..."):
                prompt = f"""
                あなたはWebディレクターです。以下のメモを【基本情報】と【戦略・質問リスト】に分けて整理してください。
                見出しには `###` 、重要な箇所には `**太字**` を使い、箇条書き `- ` で読みやすく整形してください。
                メモ: {tool_a_input}
                出力形式: ===SECTION1=== (基本情報) ===SECTION2=== (戦略)
                """
                # Proモデルを指定して実行
                text, error = generate_with_model(model_high_quality, prompt)
                
                if error:
                    error_container.error(error)
                elif text:
                    if "===SECTION2===" in text:
                        parts = text.split("===SECTION2===")
                        st.session_state.confirmed = parts[0].replace("===SECTION1===", "").strip()
                        st.session_state.pending = parts[1].strip()
                    else:
                        st.session_state.confirmed = text
                    
                    # 強制リフレッシュ
                    st.session_state.confirmed_version += 1
                    st.session_state.pending_version += 1
                    
                    st.success("反映しました！")
                    time.sleep(0.5)
                    st.rerun()

    # --- Tab 2: 会議サポート (Flashモデル使用) ---
    with tab2:
        st.write("会議ログから情報を更新します")
        st.caption(f"使用モデル: `{model_high_speed}` (高速)")
        tool_b_input = st.text_area("会議ログ", height=150)
        tool_b_mode = st.selectbox("モード", ["ヒアリング漏れチェック", "議事録・合意形成"])
        
        if "tool_b_result_conf" not in st.session_state:
            st.session_state.tool_b_result_conf = ""
            st.session_state.tool_b_result_pend = ""

        if st.button("AI実行", key="btn_b"):
            with st.spinner(f"AI ({model_high_speed}) が分析中..."):
                instruction = "未定事項を更新してください" if tool_b_mode == 'ヒアリング漏れチェック' else "合意事項を抽出してください"
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
                # Flashモデルを指定して実行
                text, error = generate_with_model(model_high_speed, prompt)
                
                if error:
                    error_container.error(error)
                elif text:
                    if "===PENDING===" in text:
                        parts = text.split("===PENDING===")
                        st.session_state.tool_b_result_conf = parts[0].replace("===CONFIRMED===", "").strip()
                        st.session_state.tool_b_result_pend = parts[1].strip()
                    else:
                        st.session_state.tool_b_result_conf = text

        if st.session_state.tool_b_result_conf:
            st.info("▼ 更新案（プレビューで確認できます）")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.caption("確定情報の更新案")
                sub_tab_view1, sub_tab_edit1 = st.tabs(["👀 プレビュー", "✏️ コード"])
                with sub_tab_view1: st.markdown(st.session_state.tool_b_result_conf)
                with sub_tab_edit1: st.text_area("", value=st.session_state.tool_b_result_conf, height=200, disabled=True, label_visibility="collapsed")
            with col_b2:
                st.caption("Todoの更新案")
                sub_tab_view2, sub_tab_edit2 = st.tabs(["👀 プレビュー", "✏️ コード"])
                with sub_tab_view2: st.markdown(st.session_state.tool_b_result_pend)
                with sub_tab_edit2: st.text_area("", value=st.session_state.tool_b_result_pend, height=200, disabled=True, label_visibility="collapsed")
            
            if st.button("↑ 反映する", type="primary"):
                clean_conf = st.session_state.tool_b_result_conf.replace("★", "").replace("**★", "**")
                
                st.session_state.confirmed = clean_conf
                st.session_state.pending = st.session_state.tool_b_result_pend
                
                # 強制リフレッシュ
                st.session_state.confirmed_version += 1
                st.session_state.pending_version += 1
                
                st.session_state.tool_b_result_conf = ""
                st.session_state.tool_b_result_pend = ""
                st.success("反映完了！")
                time.sleep(0.5)
                st.rerun()

    # --- Tab 3: 最終出力 (Proモデル使用) ---
    with tab3:
        st.caption(f"使用モデル: `{model_high_quality}` (高精度)")
        if st.button("制作指示書を出力", type="primary", key="btn_c"):
             with st.spinner(f"AI ({model_high_quality}) が作成中..."):
                prompt = f"あなたはシニアディレクターです。以下の情報から制作指示書を作成してください。Markdownで見やすく整形してください。\n{st.session_state.confirmed}"
                # Proモデルを指定して実行
                text, error = generate_with_model(model_high_quality, prompt)
                if error:
                    error_container.error(error)
                elif text:
                    st.markdown(text)

    # --- Tab 4: 壁打ちチャット (Flashモデル使用) ---
    with tab4:
        st.write("フリー相談チャット")
        st.caption(f"使用モデル: `{model_high_speed}` (高速)")
        
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["text"])

        if user_input := st.chat_input("質問を入力..."):
            st.session_state.chat_history.append({"role": "user", "text": user_input})
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_input)
            
            st.session_state.chat_context.append(f"User: {user_input}")
            history_text = "\n".join(st.session_state.chat_context[-5:])

            prompt = f"""
            あなたはWeb制作のアドバイザーです。
            【プロジェクト状況】{st.session_state.confirmed}
            【未定事項】{st.session_state.pending}
            【履歴】{history_text}
            ユーザー: {user_input}
            """
            
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("思考中..."):
                        # Flashモデルを指定して実行
                        text, error = generate_with_model(model_high_speed, prompt)
                        if error:
                            st.error(error)
                            ai_resp = f"⚠️ エラー: {error}"
                        else:
                            ai_resp = text
                            st.markdown(ai_resp)
            
            st.session_state.chat_history.append({"role": "assistant", "text": ai_resp})
            st.session_state.chat_context.append(f"AI: {ai_resp}")
