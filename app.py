import datetime
import json
import math
import os
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from streamlit_cookies_controller import CookieController

# 画面の基本設定
st.set_page_config(page_title="雀荘レーティング＆成績管理", layout="centered")

# --- GitHub APIの設定 ---
# ローカル開発時は環境変数、Streamlit Cloudでは st.secrets から取得
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO") or os.environ.get("GITHUB_REPO")
FILE_PATH = "mahjong_data.json"  # リポジトリ内に保存されるファイル名


def github_api_request(method, url, data=None):
    """GitHub APIを叩く共通ヘルパー関数"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    if method == "GET":
        return requests.get(url, headers=headers)
    elif method == "PUT":
        return requests.put(url, headers=headers, json=data)


# クッキーコントローラーの初期化
if "cookies_initialized" not in st.session_state:
    try:
        st.session_state["controller"] = CookieController()
        st.session_state["cookies_initialized"] = True
    except Exception:
        st.session_state["controller"] = None
        st.session_state["cookies_initialized"] = False


def get_dan_name(rating):
    """レーティングの数値から、自動で段位（動物名）を返す"""
    if rating <= 1349:
        return "🦥 ナマケモノ級"
    elif rating <= 1449:
        return "🦝 アライグマ級"
    elif rating <= 1549:
        return "🐻 マレーグマ級"
    elif rating <= 1649:
        return "🐼 ジャイアントパンダ級"
    elif rating <= 1749:
        return "👓 メガネグマ級"
    elif rating <= 1849:
        return "🧗 ナマケグマ級"
    elif rating <= 1949:
        return "🌙 ツキノワグマ級"
    elif rating <= 2049:
        return "🌲 アメリカクロクマ級"
    elif rating <= 2149:
        return "🪵 ヒグマ級"
    else:
        return "❄️ ホッキョクグマ級"


def load_data():
    """GitHubから最新データを取得。初回やエラー時はセッションの初期値を返す"""
    # メモリ上の初期化
    if "db_games" not in st.session_state:
        st.session_state["db_games"] = pd.DataFrame(
            columns=["試合日", "1位", "2位", "3位", "4位"]
        )
    if "db_members" not in st.session_state:
        st.session_state["db_members"] = pd.DataFrame(
            [
                {
                    "名前": "くま",
                    "Web用表示名": "くま.",
                    "ログインID": "user_1234",
                    "パスワード": "12345678",
                    "初期レート": 1500.0,
                    "現在のレート": 1500.0,
                }
            ]
        )
    if "db_logs" not in st.session_state:
        st.session_state["db_logs"] = pd.DataFrame(
            columns=["閲覧日時", "ログインID", "名前"]
        )

    # 1ブラウザセッション内で、すでにロードが完了していればスキップして高速化
    if st.session_state.get("data_loaded_from_github", False):
        return (
            st.session_state["db_games"],
            st.session_state["db_members"],
            st.session_state["db_logs"],
        )

    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.warning(
            "GitHubの認証設定が見つからないため、一時メモリモードで動作しています。"
        )
        return (
            st.session_state["db_games"],
            st.session_state["db_members"],
            st.session_state["db_logs"],
        )

    # GitHubからJSONを取得
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    res = github_api_request("GET", url)

    if res.status_code == 200:
        import base64

        content_b64 = res.json().get("content", "")
        # GitHubのsha（ファイル識別子）を次回上書き用に保存
        st.session_state["github_sha"] = res.json().get("sha")

        if content_b64:
            try:
                raw_data = json.loads(
                    base64.b64decode(content_b64).decode("utf-8")
                )
                st.session_state["db_games"] = pd.DataFrame(raw_data["games"])
                st.session_state["db_members"] = pd.DataFrame(
                    raw_data["members"]
                )
                st.session_state["db_logs"] = pd.DataFrame(raw_data["logs"])
                st.session_state["data_loaded_from_github"] = True
            except Exception as e:
                st.error(f"データ解析エラー: {e}")

    return (
        st.session_state["db_games"],
        st.session_state["db_members"],
        st.session_state["db_logs"],
    )


def save_excel(df_g, df_m, df_l):
    """最新データをメモリへ保存すると同時に、GitHubリポジトリへコミット＆プッシュする"""
    import base64

    # 1. まずはセッション状態（メモリ）を更新
    st.session_state["db_games"] = df_g
    st.session_state["db_members"] = df_m
    st.session_state["db_logs"] = df_l

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    # 2. JSONデータを作成
    data_payload = {
        "games": df_g.to_dict(orient="records"),
        "members": df_m.to_dict(orient="records"),
        "logs": df_l.to_dict(orient="records"),
    }
    json_str = json.dumps(data_payload, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    # 3. 最新の sha を取得（コンフリクト防止）
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    res_get = github_api_request("GET", url)
    sha = (
        res_get.json().get("sha")
        if res_get.status_code == 200
        else st.session_state.get("github_sha")
    )

    # 4. GitHubへデータを送信（コミット）
    commit_data = {
        "message": f"📊 雀荘データ自動更新 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
        "content": content_b64,
    }
    if sha:
        commit_data["sha"] = sha

    res_put = github_api_request("PUT", url, data=commit_data)

    if res_put.status_code in [200, 201]:
        st.session_state["github_sha"] = res_put.json()["content"]["sha"]
    else:
        st.error(
            f"GitHubへの保存に失敗しました。ステータスコード: {res_put.status_code}"
        )


def calculate_all_ratings(df_g, df_m):
    """過去の全対局からレーティングの推移を計算する"""
    p_rt = {n: 1500.0 for n in df_m["名前"]}
    rt_hist = {n: [1500.0] for n in df_m["名前"]}
    if df_g.empty:
        return p_rt, rt_hist

    df_g_sorted = df_g.sort_values(by="試合日").copy()
    for _, row in df_g_sorted.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]
        for p in p_list:
            if p not in p_rt:
                p_rt[p], rt_hist[p] = 1500.0, [1500.0]
        r = [p_rt[p] for p in p_list]
        K, change = 32, {p: 0.0 for p in p_list}
        for i in range(4):
            for j in range(4):
                if i != j:
                    E_i = 1 / (1 + math.pow(10, (r[j] - r[i]) / 400))
                    change[p_list[i]] += K * ((1.0 if i < j else 0.0) - E_i)
        for p in p_list:
            p_rt[p] += change[p]
            rt_hist[p].append(p_rt[p])
    return p_rt, rt_hist


def calculate_personal_stats(df_g, p_name):
    """個人の月間・年間成績を正確に計算する"""
    default_stats = {
        "月間対戦数": 0,
        "月間平均": 0.0,
        "月間トップ": 0.0,
        "月間ラス": 0.0,
        "月間着順回数": {1: 0, 2: 0, 3: 0, 4: 0},
        "年間対戦数": 0,
        "年間平均": 0.0,
        "年間トップ": 0.0,
        "年間ラス": 0.0,
        "年間着順回数": {1: 0, 2: 0, 3: 0, 4: 0},
    }
    if df_g.empty:
        return default_stats
    df_g_copy = df_g.copy()
    df_g_copy["試合日"] = pd.to_datetime(df_g_copy["試合日"])
    now = datetime.datetime.now()
    melted = [
        df_g_copy[["試合日", f"{r}位"]].rename(columns={f"{r}位": "名前"}).assign(着順=r)
        for r in range(1, 5)
    ]
    df_all = pd.concat(melted, ignore_index=True)
    df_p = df_all[df_all["名前"] == p_name]
    if df_p.empty:
        return default_stats
    df_m = df_p[
        (df_p["試合日"].dt.year == now.year)
        & (df_p["試合日"].dt.month == now.month)
    ]
    df_y = df_p[df_p["試合日"].dt.year == now.year]
    m_count, y_count = len(df_m), len(df_y)
    return {
        "月間対戦数": m_count,
        "月間平均": round(df_m["着順"].mean(), 2) if m_count > 0 else 0.0,
        "月間トップ": (
            round(len(df_m[df_m["着順"] == 1]) / m_count * 100, 1)
            if m_count > 0
            else 0.0
        ),
        "月間ラス": (
            round(len(df_m[df_m["着順"] == 4]) / m_count * 100, 1)
            if m_count > 0
            else 0.0
        ),
        "月間着順回数": {r: len(df_m[df_m["着順"] == r]) for r in range(1, 5)},
        "年間対戦数": y_count,
        "年間平均": round(df_y["着順"].mean(), 2) if y_count > 0 else 0.0,
        "年間トップ": (
            round(len(df_y[df_y["着順"] == 1]) / y_count * 100, 1)
            if y_count > 0
            else 0.0
        ),
        "年間ラス": (
            round(len(df_y[df_y["着順"] == 4]) / y_count * 100, 1)
            if y_count > 0
            else 0.0
        ),
        "年間着順回数": {r: len(df_y[df_y["着順"] == r]) for r in range(1, 5)},
    }


def get_personal_history(df_g, p_name):
    """個人の過去の対局履歴を取得する"""
    if df_g.empty:
        return pd.DataFrame()
    rows = []
    for _, row in df_g.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]
        if p_name in p_list:
            rows.append(
                {
                    "対戦日": row["試合日"],
                    "あなたの着順": f"{p_list.index(p_name)+1}着",
                    "1位": row["1位"],
                    "2位": row["2位"],
                    "3位": row["3位"],
                    "4位": row["4位"],
                }
            )
    return (
        pd.DataFrame(rows).sort_values(by="対戦日", ascending=False)
        if rows
        else pd.DataFrame()
    )


def generate_login_info(name):
    """新規客用のID・PWを生成する"""
    import secrets
    import string

    rid = f"user_{secrets.randbelow(9000)+1000}"
    rpw = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
    )
    return f"{name}.", rid, rpw


# --- データのロードと初期実行 ---
df_games, df_members, df_logs = load_data()
player_ratings, rating_history = calculate_all_ratings(df_games, df_members)
for n, v in player_ratings.items():
    df_members.loc[df_members["名前"] == n, "現在のレート"] = round(v, 1)

if "logged_in" not in st.session_state:
    st.session_state.update({"logged_in": False, "user_name": ""})
if st.session_state["cookies_initialized"] and not st.session_state["logged_in"]:
    sid, spw = st.session_state["controller"].get(
        "saved_login_id"
    ), st.session_state["controller"].get("saved_login_pw")
    if sid and spw:
        user = df_members[
            (df_members["ログインID"] == sid)
            & (df_members["パスワード"].astype(str) == spw)
        ]
        if not user.empty:
            st.session_state.update(
                {"logged_in": True, "user_name": str(user["名前"].values[0])}
            )

menu = st.sidebar.radio("メニュー", ["お客様ページ", "スタッフ専用入力画面"])

if menu == "スタッフ専用入力画面":
    st.header("💻 スタッフ専用・対局結果管理")
    
    # パスワード入力（※入力されたら、以下の処理をすべてインデント内で実行する）
    if st.text_input("管理用パスワード", type="password") == "admin123":
        st.success("認証されました。")
        
        # タブに「👤 メンバーアカウント管理」を追加して3つに拡張
        t1, t2, t3 = st.tabs(["📝 新規登録", "🗂️ 過去データ確認·修正", "👤 メンバーアカウント管理"])
        
        with t1:
            with st.form("input_form", clear_on_submit=True):
                g_dt = st.date_input("試合日", datetime.date.today())
                p1, p2, p3, p4 = st.text_input("1位"), st.text_input("2位"), st.text_input("3位"), st.text_input("4位")
                if st.form_submit_button("保存・確定"):
                    if p1 and p2 and p3 and p4 and len({p1, p2, p3, p4}) == 4:
                        for p in [p1, p2, p3, p4]:
                            if p not in df_members["名前"].values:
                                w_n, rid, rpw = generate_login_info(p)
                                df_members = pd.concat([df_members, pd.DataFrame([{"名前":p,"Web用表示名":w_n,"ログインID":rid,"パスワード":rpw,"初期レート":1500.0,"現在のレート":1500.0}])], ignore_index=True)
                                st.info(f"🆕 新規客: 【{p}】 ID:{rid} PW:{rpw}")
                        df_games = pd.concat([df_games, pd.DataFrame([{"試合日":g_dt.strftime("%Y-%m-%d"),"1位":p1,"2位":p2,"3位":p3,"4位":p4}])], ignore_index=True)
                        save_excel(df_games, df_members, df_logs)
                        st.success("保存しました！")
                        st.session_state["data_loaded_from_github"] = False
                        st.rerun()
                    else: st.error("入力欄に不備があります。")
                    
        with t2:
            st.subheader("対局データの確認・修正")
            edt_g = st.data_editor(df_games, num_rows="dynamic", use_container_width=True, key="editor_games")
            if st.button("💾 対局データをシステム内に上書き保存"):
                save_excel(edt_g, df_members, df_logs)
                st.success("対局データを上書き保存しました！")
                st.session_state["data_loaded_from_github"] = False
                st.rerun()
                
        with t3:
            st.subheader("👤 登録メンバーのID・パスワード確認と修正")
            st.caption("新規登録者のIDやパスワードを忘れた場合は、ここからいつでも確認や再設定（変更）が可能です。")
            # パスワードを含めたメンバーマスタをそのまま編集・確認できるテーブルを表示
            edt_m = st.data_editor(df_members, num_rows="dynamic", use_container_width=True, key="editor_members")
            if st.button("💾 メンバー情報をシステム内に上書き保存"):
                save_excel(df_games, edt_m, df_logs)
                st.success("メンバー情報を上書き保存しました！")
                st.session_state["data_loaded_from_github"] = False
                st.rerun()
else:
    if not st.session_state["logged_in"]:
        st.subheader("🔑 プレイヤーログイン")
        uid, upw, rem = (
            st.text_input("ログインID"),
            st.text_input("パスワード", type="password"),
            st.checkbox("ログイン情報を記憶する", value=True),
        )
        if st.button("ログイン") and uid and upw:
            user = df_members[
                (df_members["ログインID"] == uid)
                & (df_members["パスワード"].astype(str) == upw)
            ]
            if not user.empty:
                uname = str(user.iloc[0]["名前"])
                st.session_state.update({"logged_in": True, "user_name": uname})
                if rem and st.session_state["cookies_initialized"]:
                    st.session_state["controller"].set("saved_login_id", uid)
                    st.session_state["controller"].set("saved_login_pw", upw)
                df_logs = pd.concat(
                    [
                        df_logs,
                        pd.DataFrame(
                            [
                                {
                                    "閲覧日時": datetime.datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "ログインID": uid,
                                    "名前": uname,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
                save_excel(df_games, df_members, df_logs)
                st.success(f"ようこそ、{uname} さん！")
                st.session_state["data_loaded_from_github"] = False
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います。")
    else:
        st.sidebar.write(f"ログイン: {st.session_state['user_name']} さん")
        if st.sidebar.button("ログアウト（記憶消去）"):
            st.session_state.update({"logged_in": False, "user_name": ""})
            if st.session_state["cookies_initialized"]:
                st.session_state["controller"].remove("saved_login_id")
                st.session_state["controller"].remove("saved_login_pw")
            st.rerun()

        tab1, tab2 = st.tabs(["📊 マイデータ", "🏆 総合ランキング"])
        with tab1:
            my_name = st.session_state["user_name"]
            st.header(f"👤 {my_name} さんのマイページ")
            p_stats = calculate_personal_stats(df_games, my_name)

            my_rate_df = df_members[df_members["名前"] == my_name]
            my_rt_val = (
                my_rate_df["現在のレート"].values[0]
                if not my_rate_df.empty
                else 1500.0
            )
            dan_name = get_dan_name(my_rt_val)

            st.metric(label="現在のレーティング", value=f"{my_rt_val} Rt")
            st.header(f"🏆 現在の階級：{dan_name}")
            st.write("---")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🌙 月間成績")
                st.write(
                    f"**平均着順:** {p_stats['月間平均']} 着\n\n**トップ率:** {p_stats['月間トップ']} %\n\n**ラス率:** {p_stats['月間ラス']} %"
                )
                m_rc = p_stats["月間着順回数"]
                st.write(
                    f"**着順内訳:** 1着:{m_rc[1]}回 / 2着:{m_rc[2]}回 / 3着:{m_rc[3]}回 / 4着:{m_rc[4]}回"
                )
                st.write(f"**対戦数:** {p_stats['月間対戦数']} / 30 戦")
                if p_stats["月間対戦数"] < 30:
                    st.progress(p_stats["月間対戦数"] / 30)
                    st.caption(f"あと **{30 - p_stats['月間対戦数']}戦**")
                else:
                    st.success("🎉 月間規定打数クリア！")
            with col2:
                st.subheader("☀️ 年間成績")
                st.write(
                    f"**平均着順:** {p_stats['年間平均']} 着\n\n**トップ率:** {p_stats['年間トップ']} %\n\n**ラス率:** {p_stats['年間ラス']} %"
                )
                y_rc = p_stats["年間着順回数"]
                st.write(
                    f"**着順内訳:** 1着:{y_rc[1]}回 / 2着:{y_rc[2]}回 / 3着:{y_rc[3]}回 / 4着:{y_rc[4]}回"
                )
                st.write(f"**対戦数:** {p_stats['年間対戦数']} / 360 戦")
                if p_stats["年間対戦数"] < 360:
                    st.progress(p_stats["年間対戦数"] / 360)
                    st.caption(f"あと **{360 - p_stats['年間対戦数']}戦**")
                else:
                    st.success("🎉 年間規定打数クリア！")

            st.subheader("🗂️ 直近の対局履歴（対戦相手）")
            df_hist = get_personal_history(df_games, my_name)
            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("対局履歴がありません。")

            st.subheader("📊 着順内訳の割合（通算）")
            df_g_copy = df_games.copy()
            melted_all = [
                df_g_copy[[f"{r}位"]]
                .rename(columns={f"{r}位": "名前"})
                .assign(着順=f"{r}着")
                for r in range(1, 5)
            ]
            df_all_flat = pd.concat(melted_all, ignore_index=True)
            df_my_ranks = df_all_flat[df_all_flat["名前"] == my_name]

            if not df_my_ranks.empty:
                rank_counts = df_my_ranks["着順"].value_counts().reset_index()
                rank_counts.columns = ["着順", "回数"]
                rank_counts["sort"] = rank_counts["着順"].str.get(0).astype(int)
                rank_counts = rank_counts.sort_values("sort")
                fig_pie = px.pie(
                    rank_counts,
                    values="回数",
                    names="着順",
                    hole=0.3,
                    color="着順",
                    color_discrete_map={
                        "1着": "#1f77b4",
                        "2着": "#aec7e8",
                        "3着": "#ffbb78",
                        "4着": "#ff7f0e",
                    },
                )
                fig_pie.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    textfont_size=18,
                    insidetextfont=dict(color="white", weight="bold"),
                )
                fig_pie.update_layout(legend=dict(font=dict(size=14)))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("円グラフを表示するための対局データがありません。")

            st.subheader("📈 レーティング推移")
            if my_name in rating_history and len(rating_history[my_name]) > 1:
                df_chart = pd.DataFrame(
                    {
                        "対戦回数": list(range(len(rating_history[my_name]))),
                        "レーティング": rating_history[my_name],
                    }
                )
                st.plotly_chart(
                    px.line(
                        df_chart,
                        x="対戦回数",
                        y="レーティング",
                        title="Rt変動トレンド",
                        markers=True,
                    ),
                    use_container_width=True,
                )
            else:
                st.info("十分な対局データがありません。")

        with tab2:
            st.header("店舗総合トップ10")
            st.write("※平均着順2.5以下の方が対象（名前は匿名化）")
            if not df_games.empty:
                df_g_all = df_games.copy()
                df_g_all["試合日"] = pd.to_datetime(df_g_all["試合日"])
                now = datetime.datetime.now()
                melted_all = [
                    df_g_all[["試合日", f"{r}位"]]
                    .rename(columns={f"{r}位": "名前"})
                    .assign(着順=r)
                    for r in range(1, 5)
                ]
                df_all_flat = pd.concat(melted_all, ignore_index=True)
                p_choice = st.radio(
                    "期間", ["月間（動的規定打数）", "年間（360戦以上）"]
                )

                if "月間" in p_choice:
                    df_f = df_all_flat[
                        (df_all_flat["試合日"].dt.year == now.year)
                        & (df_all_flat["試合日"].dt.month == now.month)
                    ]
                    min_g = now.day if now.day <= 25 else 30
                    st.caption(f"📢 本日のランキング掲載条件: **{min_g}半荘以上**")
                else:
                    df_f = df_all_flat[df_all_flat["試合日"].dt.year == now.year]
                    min_g = 360
                    st.caption(f"📢 年間のランキング掲載条件: **360半荘以上**")

                if not df_f.empty:
                    stats = (
                        df_f.groupby("名前")["着順"]
                        .agg(対戦数="count", average_rank="mean")
                        .reset_index()
                        .rename(columns={"average_rank": "平均着順"})
                    )
                    ranking = stats[
                        (stats["対戦数"] >= min_g) & (stats["平均着順"] <= 2.5)
                    ]
                    if not ranking.empty:
                        rk = ranking.merge(
                            df_members[
                                ["名前", "Web用表示名", "現在のレート"]
                            ],
                            on="名前",
                        )
                        rk["現在の段位"] = rk["現在のレート"].apply(
                            lambda x: get_dan_name(x)
                        )
                        rk_sorted = rk.sort_values(by="平均着順").head(10).copy()
                        rk_sorted.insert(0, "順位", range(1, len(rk_sorted) + 1))
                        st.dataframe(
                            rk_sorted[
                                [
                                    "順位",
                                    "Web用表示名",
                                    "現在の段位",
                                    "平均着順",
                                    "対戦数",
                                    "現在のレート",
                                ]
                            ],
                            use_container_width=True,
                        )
                    else:
                        st.info("条件を満たすプレイヤーはまだいません。")
                else:
                    st.info("選択された期間の対局データがありません。")
            else:
                st.info("対局データがありません。")
