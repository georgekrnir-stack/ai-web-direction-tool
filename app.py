import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
import datetime

# ==========================================
# 1. 設定・準備
# ==========================================
st.set_page_config(page_title="AI Director Assistant", layout="wide")
st.title("🚀 AI Web Direction Assistant (v13.1 Summary Enhanced)")

# エラー表示エリア
error_container = st.container()

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    
    api_key = st.text_input("Gemini API Key", type="password")
    
    # モデル自動割り当て設定
    st.caption("タスクに応じて最適なモデルを自動で使用します")
    with st.expander("モデル設定の詳細"):
        model_high_quality = st.text_input("高精度 (分析・出力)", value="gemini-2.5-pro")
        model_high_speed = st.text_input("高速 (会議・チャット)", value="gemini-2.5-flash")
    
    if api_key:
        genai.configure(api_key=api_key)
        if st.button("📡 接続テスト"):
            with st.spinner("確認中..."):
                try:
                    test_model = genai.GenerativeModel(model_high_speed)
                    st.success("✅ 接続OK")
                except Exception as e:
                    st.error(f"❌ エラー: {e}")
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
if "confirmed_version" not in st.session_state: st.session_state.confirmed_version = 0

if "pending" not in st.session_state:
    st.session_state.pending = """### 【次回確認事項】
- 
"""
if "pending_version" not in st.session_state: st.session_state.pending_version = 0

if "full_transcript" not in st.session_state:
    st.session_state.full_transcript = "" 

# 会議サポートの出力履歴用
if "meeting_support_history" not in st.session_state:
    st.session_state.meeting_support_history = []

# 打ち合わせ後まとめの出力一時保存
if "post_meeting_conf" not in st.session_state: st.session_state.post_meeting_conf = ""
if "post_meeting_pend" not in st.session_state: st.session_state.post_meeting_pend = ""

if "chat_history" not in st.session_state: st.session_state.chat_history = [] 
if "chat_context" not in st.session_state: st.session_state.chat_context = [] 

# ==========================================
# 3. 共通関数
# ==========================================
def generate_with_model(model_name, prompt):
    if not api_key: return None, "APIキー未設定"
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts: return None, "応答が空です"
        return response.text, None
    except Exception as e:
        return None, str(e)

# ==========================================
# 4. 画面レイアウト
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左カラム（バイブル） ---
with left_col:
    st.subheader("📘 プロジェクト・バイブル")
    
    st.caption("▼ 確定情報 (Master)")
    tab_conf_view, tab_conf_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    with tab_conf_edit:
        conf_key = f"confirmed_{st.session_state.confirmed_version}"
        new_confirmed = st.text_area("確定情報", value=st.session_state.confirmed, height=300, key=conf_key, label_visibility="collapsed")
        st.session_state.confirmed = new_confirmed
    with tab_conf_view:
        st.markdown(st.session_state.confirmed)

    st.markdown("---")

    st.caption("▼ 未定・Todo (Task)")
    tab_pend_view, tab_pend_edit = st.tabs(["👀 プレビュー", "✏️ 編集"])
    with tab_pend_edit:
        pend_key = f"pending_{st.session_state.pending_version}"
        new_pending = st.text_area("未定事項", value=st.session_state.pending, height=200, key=pend_key, label_visibility="collapsed")
        st.session_state.pending = new_pending
    with tab_pend_view:
        st.markdown(st.session_state.pending)

# --- 右カラム（AIツール） ---
with right_col:
    st.subheader("🛠️ AIツール")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📨 事前分析", 
        "🗣️ 会議サポート", 
        "📝 打ち合わせ後まとめ", 
        "📑 最終出力", 
        "💡 壁打ち"
    ])

    # --- Tab 1: 事前分析 ---
    with tab1:
        st.write("メモから情報を整理します")
        tool_a_input = st.text_area("メモを入力", height=100)
        if st.button("分析実行", key="btn_a"):
            with st.spinner(f"分析中 ({model_high_quality})..."):
                prompt = f"""
                あなたはWebディレクターです。以下のメモを【基本情報】と【戦略・質問リスト】に分けて整理してください。
                Markdown形式で見やすく整形してください。
                メモ: {tool_a_input}
                出力形式: ===SECTION1=== (基本情報) ===SECTION2=== (戦略)
                """
                text, error = generate_with_model(model_high_quality, prompt)
                if text:
                    if "===SECTION2===" in text:
                        parts = text.split("===SECTION2===")
                        st.session_state.confirmed = parts[0].replace("===SECTION1===", "").strip()
                        st.session_state.pending = parts[1].strip()
                    else:
                        st.session_state.confirmed = text
                    st.session_state.confirmed_version += 1
                    st.session_state.pending_version += 1
                    st.success("反映しました")
                    time.sleep(0.5)
                    st.rerun()
                elif error: error_container.error(error)

    # --- Tab 2: 会議サポート ---
    with tab2:
        st.markdown("### 🗣️ 会議サポート")
        st.caption(f"使用モデル: `{model_high_speed}` (高速)")
        
        # ログ入力（追記型）
        new_log_input = st.text_area("今回の会話ログ（追記されます）", height=100, placeholder="ここに録音テキストを貼り付け...", key="meeting_log_input")
        
        st.markdown("**実行したいタスクを選択（複数可）:**")
        check_summary = st.checkbox("打ち合わせ内容のまとめ")
        check_issues = st.checkbox("矛盾点や問題点などの抽出")
        check_leak = st.checkbox("ヒアリング漏れチェック")
        check_proposal = st.checkbox("これまでの打ち合わせ内容から提案内容を作成")

        if st.button("AI実行", key="btn_b"):
            if not new_log_input and not st.session_state.full_transcript:
                st.warning("ログがありません。入力してください。")
            elif not (check_summary or check_issues or check_leak or check_proposal):
                st.warning("タスクを少なくとも1つ選択してください。")
            else:
                current_full_log = st.session_state.full_transcript
                if new_log_input:
                    current_full_log += "\n" + new_log_input
                    st.session_state.full_transcript = current_full_log 
                
                tasks_instruction = ""
                if check_summary: tasks_instruction += "- 今回の打ち合わせ内容の要約\n"
                if check_issues: tasks_instruction += "- 現状の発言における矛盾点や懸念される問題点\n"
                if check_leak: tasks_instruction += "- プロジェクト進行に必要な情報のヒアリング漏れ\n"
                if check_proposal: tasks_instruction += "- これまでの文脈を踏まえた、具体的な提案（構成やデザインの方向性など）\n"

                prompt = f"""
                あなたは優秀なWebディレクターのアシスタントです。
                以下の情報を基に、指定された項目について出力してください。

                【現在の確定情報】{st.session_state.confirmed}
                【現在の未定事項】{st.session_state.pending}
                【これまでの全会話ログ】{current_full_log}

                【指示：以下の項目について出力してください】
                {tasks_instruction}

                ※出力はMarkdown形式で見やすく、項目ごとに見出しを付けて整理してください。
                """

                with st.spinner("分析中..."):
                    text, error = generate_with_model(model_high_speed, prompt)
                    if text:
                        timestamp = datetime.datetime.now().strftime("%H:%M")
                        st.session_state.meeting_support_history.insert(0, {
                            "time": timestamp,
                            "content": text,
                            "tasks": tasks_instruction
                        })
                        st.success("出力完了")
                    elif error:
                        error_container.error(error)

        st.markdown("---")
        st.markdown("#### 📝 出力履歴")
        if not st.session_state.meeting_support_history:
            st.caption("まだ履歴はありません。")
        
        for i, item in enumerate(st.session_state.meeting_support_history):
            with st.expander(f"出力 #{len(st.session_state.meeting_support_history)-i} ({item['time']})", expanded=(i==0)):
                st.markdown(item['content'])

    # --- Tab 3: 打ち合わせ後まとめ（機能追加版） ---
    with tab3:
        st.markdown("### 📝 打ち合わせ後まとめ")
        st.caption(f"使用モデル: `{model_high_quality}` (高精度)")
        st.info("全ての会議ログとバイブル情報を統合し、プロジェクトの全体像を再構築します。")

        # 1. 全ログの確認・編集
        st.markdown("#### 1. 会議ログの確認・修正")
        edited_transcript = st.text_area(
            "これまでの全会話ログ（必要に応じて修正してください）",
            value=st.session_state.full_transcript,
            height=200,
            key="edited_transcript_view"
        )
        # 修正があれば保存
        if edited_transcript != st.session_state.full_transcript:
            st.session_state.full_transcript = edited_transcript

        # 2. ディレクターメモ
        st.markdown("#### 2. ディレクター所感・メモ")
        director_memo = st.text_area(
            "AIに伝えたいニュアンスや補足事項を入力",
            height=100,
            placeholder="例：クライアントは予算よりも納期を気にしている様子だった。デザインはA案の方向で進めたい。"
        )

        if st.button("まとめを作成（確定情報の更新案）", key="btn_post_meeting"):
            if not st.session_state.full_transcript:
                st.warning("会議ログがまだありません。")
            else:
                with st.spinner(f"全体分析中 ({model_high_quality})..."):
                    prompt = f"""
                    あなたは統括ディレクターです。
                    これまでの全ての会議ログ、ディレクターのメモ、現在のプロジェクト情報を統合し、
                    **「最新の確定情報」と「残課題」**を整理してください。

                    【現在の確定情報】
                    {st.session_state.confirmed}

                    【現在の未定事項】
                    {st.session_state.pending}

                    【全会議ログ】
                    {st.session_state.full_transcript}
                    
                    【ディレクターからの重要メモ・所感】
                    {director_memo}

                    【指示】
                    1. ログ全体とディレクターメモを分析し、確定情報を最新化・詳細化してください。（変更点には★をつける）
                    2. ディレクターのメモにある意図を汲み取り、バイブルに反映させてください。
                    3. 解決した未定事項を消し、新たに出た課題をTodoリストに追加してください。
                    
                    出力形式: ===CONFIRMED=== (内容) ===PENDING=== (内容)
                    """
                    
                    text, error = generate_with_model(model_high_quality, prompt)
                    if text:
                        if "===PENDING===" in text:
                            parts = text.split("===PENDING===")
                            st.session_state.post_meeting_conf = parts[0].replace("===CONFIRMED===", "").strip()
                            st.session_state.post_meeting_pend = parts[1].strip()
                        else:
                            st.session_state.post_meeting_conf = text
                            st.session_state.post_meeting_pend = st.session_state.pending
                    elif error:
                        error_container.error(error)

        # 結果表示と反映ボタン
        if st.session_state.post_meeting_conf:
            st.success("✅ **分析完了（更新案）**")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.caption("確定情報の更新案")
                st.text_area("", value=st.session_state.post_meeting_conf, height=300, disabled=True)
            with col_b2:
                st.caption("Todoの更新案")
                st.text_area("", value=st.session_state.post_meeting_pend, height=300, disabled=True)
            
            if st.button("↑ バイブルに反映する", type="primary", key="reflect_post_meeting"):
                clean_conf = st.session_state.post_meeting_conf.replace("★", "").replace("**★", "**")
                st.session_state.confirmed = clean_conf
                st.session_state.pending = st.session_state.post_meeting_pend
                
                st.session_state.confirmed_version += 1
                st.session_state.pending_version += 1
                
                st.session_state.post_meeting_conf = ""
                st.session_state.post_meeting_pend = ""
                
                st.success("反映完了！")
                time.sleep(0.5)
                st.rerun()

    # --- Tab 4: 最終出力 ---
    with tab4:
        if st.button("指示書を出力", type="primary", key="btn_c"):
             with st.spinner(f"作成中 ({model_high_quality})..."):
                prompt = f"以下の確定情報から制作指示書を作成してください。\n{st.session_state.confirmed}"
                text, error = generate_with_model(model_high_quality, prompt)
                if text: st.markdown(text)
                elif error: error_container.error(error)

    # --- Tab 5: 壁打ち ---
    with tab5:
        st.write("フリー相談")
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]): st.markdown(msg["text"])

        if user_input := st.chat_input("質問..."):
            st.session_state.chat_history.append({"role": "user", "text": user_input})
            with chat_container:
                with st.chat_message("user"): st.markdown(user_input)
            
            st.session_state.chat_context.append(f"User: {user_input}")
            history = "\n".join(st.session_state.chat_context[-5:])
            prompt = f"【状況】{st.session_state.confirmed}\n【履歴】{history}\nUser: {user_input}"
            
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("..."):
                        text, error = generate_with_model(model_high_speed, prompt)
                        if text: st.markdown(text)
                        elif error: st.error(error)
            
            if text:
                st.session_state.chat_history.append({"role": "assistant", "text": text})
                st.session_state.chat_context.append(f"AI: {text}")
