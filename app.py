def load_data():
    """【強化版】最優先でGitHubから最新データを取得し、セッション内で保持する"""
    # 1. メモリ上の器（State）がなければ初期値を作成
    if "db_games" not in st.session_state:
        st.session_state["db_games"] = pd.DataFrame(columns=["試合日", "1位", "2位", "3位", "4位"])
    
    if "db_members" not in st.session_state:
        # 🌟 「くま」さんの初期データを削除し、空のデータフレームとして初期化します
        st.session_state["db_members"] = pd.DataFrame(columns=[
            "名前", "Web用表示名", "ログインID", "パスワード", "初期レート", "現在のレート"
        ])
        
    if "db_logs" not in st.session_state:
        st.session_state["db_logs"] = pd.DataFrame(columns=["閲覧日時", "ログインID", "名前"])
