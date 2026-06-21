import datetime
import io
import math
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_cookies_controller import CookieController

# ネット（Secrets）保存用のダミーファイルパス
EXCEL_FILE = "mahjong_system.xlsx"

st.set_page_config(page_title="雀荘レーティング＆成績管理", layout="centered")

# クッキーコントローラーの初期化
if "cookies_initialized" not in st.session_state:
    try:
        st.session_state["controller"] = CookieController()
        st.session_state["cookies_initialized"] = True
    except Exception:
        st.session_state["controller"] = None
        st.session_state["cookies_initialized"] = False


def load_data():
    """SecretsまたはローカルのExcelからデータを安全に読み込む"""
    # ネット公開（Streamlit Cloud）環境の場合、Secretsのテキストデータを読み込む
    if "data" in st.secrets:
        import io

        g_csv = st.secrets["data"]["games"]
        m_csv = st.secrets["data"]["members"]
        l_csv = st.secrets["data"]["logs"]

        df_g = pd.read_csv(io.StringIO(g_csv.strip()))
        df_m = pd.read_csv(io.StringIO(m_csv.strip()))
        try:
            df_l = pd.read_csv(io.StringIO(l_csv.strip()))
        except Exception:
            df_l = pd.DataFrame(columns=["閲覧日時", "ログインID", "名前"])
    else:
        # ローカル環境のバックアップ用（実物のExcelを読み込む）
        df_g = pd.read_excel(EXCEL_FILE, sheet_name="対局入力")
        df_m = pd.read_excel(EXCEL_FILE, sheet_name="メンバーマスタ")
        try:
            df_l = pd.read_excel(EXCEL_FILE, sheet_name="ログインログ")
        except Exception:
            df_l = pd.DataFrame(columns=["閲覧日時", "ログインID", "名前"])

    if "初期レート" not in df_m.columns:
        df_m["初期レート"] = 1500.0
    if "現在のレート" not in df_m.columns:
        df_m["現在のレート"] = 1500.0

    return df_g, df_m, df_l


def save_excel(df_g, df_m, df_l):
    """データを保存する（ネット環境では画面へ一時反映、ローカルではExcelへ保存）"""
    if "data" in st.secrets:
        # ネット上では、入力されたデータを即座に画面へ反映させるためにデータを一時保持
        st.session_state["temporary_df_games"] = df_g
        st.session_state["temporary_df_members"] = df_m
        st.session_state["temporary_df_logs"] = df_l
    else:
        # ローカル環境（お店のパソコン）では通常通りExcelを上書きする
        with pd.ExcelWriter(
            EXCEL_FILE, mode="a", engine="openpyxl", if_sheet_exists="replace"
        ) as w:
            df_g.to_excel(w, sheet_name="対局入力", index=False)
            df_m.to_excel(w, sheet_name="メンバーマスタ", index=False)
            df_l.to_excel(w, sheet_name="ログインログ", index=False)



def calculate_all_ratings(df_g, df_m):
    """過去の全対局からレーティングの推移を計算する"""
    p_rt = {n: 1500.0 for n in df_m["名前"]}
    rt_hist = {n: [1500.0] for n in df_m["名前"]}

    if df_g.empty:
        return p_rt, rt_hist

    # 日付順に処理
    df_g_sorted = df_g.sort_values(by="試合日").copy()
    for _, row in df_g_sorted.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]

        # マスタに未登録の名前があれば初期化
        for p in p_list:
            if p not in p_rt:
                p_rt[p] = 1500.0
                rt_hist[p] = [1500.0]

        r = [p_rt[p] for p in p_list]
        K = 32
        change = {p: 0.0 for p in p_list}

        # 4人総当たりのレーティング計算
        for i in range(4):
            for j in range(4):
                if i != j:
                    E_i = 1 / (1 + math.pow(10, (r[j] - r[i]) / 400))
                    W_i = 1.0 if i < j else 0.0
                    change[p_list[i]] += K * (W_i - E_i)

        for p in p_list:
            p_rt[p] += change[p]
            rt_hist[p].append(p_rt[p])

    return p_rt, rt_hist
def calculate_personal_stats(df_g, p_name):
    """個人の月間・年間成績（平均着順・対戦数・各着順の回数・トップ率・ラス率）を計算する"""
    default_stats = {
        "月間対戦数": 0, "月間平均": 0.0, "月間トップ": 0.0, "月間ラス": 0.0, "月間着順回数": {1: 0, 2: 0, 3: 0, 4: 0},
        "年間対戦数": 0, "年間平均": 0.0, "年間トップ": 0.0, "年間ラス": 0.0, "年間着順回数": {1: 0, 2: 0, 3: 0, 4: 0}
    }
    if df_g.empty:
        return default_stats

    # 【バグ修正箇所】安全にデータをコピーして日付型に変換
    df_g_copy = df_g.copy()
    df_g_copy["試合日"] = pd.to_datetime(df_g_copy["試合日"])
    now = datetime.datetime.now()

    melted = []
    for r in range(1, 5):
        t = df_g_copy[["試合日", f"{r}位"]].rename(columns={f"{r}位": "名前"})
        t["着順"] = r
        melted.append(t)

    df_all = pd.concat(melted, ignore_index=True)
    df_p = df_all[df_all["名前"] == p_name]

    if df_p.empty:
        return default_stats

    # 月間と年間のデータ抽出
    df_m = df_p[(df_p["試合日"].dt.year == now.year) & (df_p["試合日"].dt.month == now.month)]
    df_y = df_p[df_p["試合日"].dt.year == now.year]

    # 月間の計算
    m_count = len(df_m)
    m_avg = df_m["着順"].mean() if m_count > 0 else 0.0
    m_top = (len(df_m[df_m["着順"] == 1]) / m_count * 100) if m_count > 0 else 0.0
    m_las = (len(df_m[df_m["着順"] == 4]) / m_count * 100) if m_count > 0 else 0.0
    m_ranks = {r: len(df_m[df_m["着順"] == r]) for r in range(1, 5)}

    # 年間の計算
    y_count = len(df_y)
    y_avg = df_y["着順"].mean() if y_count > 0 else 0.0
    y_top = (len(df_y[df_y["着順"] == 1]) / y_count * 100) if y_count > 0 else 0.0
    y_las = (len(df_y[df_y["着順"] == 4]) / y_count * 100) if y_count > 0 else 0.0
    y_ranks = {r: len(df_y[df_y["着順"] == r]) for r in range(1, 5)}

    return {
        "月間対戦数": m_count, "月間平均": round(m_avg, 2), "月間トップ": round(m_top, 1), "月間ラス": round(m_las, 1), "月間着順回数": m_ranks,
        "年間対戦数": y_count, "年間平均": round(y_avg, 2), "年間トップ": round(y_top, 1), "年間ラス": round(y_las, 1), "年間着順回数": y_ranks
    }

def get_personal_history(df_g, p_name):
    """個人の過去の対戦日と、その対局の1位〜4位のメンバー履歴を取得する"""
    if df_g.empty:
        return pd.DataFrame()

    rows = []
    for _, row in df_g.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]
        # 自分が参加している対局のみを抽出
        if p_name in p_list:
            my_rank = p_list.index(p_name) + 1
            rows.append(
                {
                    "対戦日": row["試合日"],
                    "あなたの着順": f"{my_rank}着",
                    "1位": row["1位"],
                    "2位": row["2位"],
                    "3位": row["3位"],
                    "4位": row["4位"],
                }
            )

    if rows:
        df_hist = pd.DataFrame(rows)
        # 日付が新しい順に並び替え
        return df_hist.sort_values(by="対戦日", ascending=False)
    else:
        return pd.DataFrame()


    if rows:
        df_hist = pd.DataFrame(rows)
        return df_hist.sort_values(by="対戦日", ascending=False)
    else:
        return pd.DataFrame()


def generate_login_info(name):
    """新規ユーザー用のID、パスワード、Web用表示名を自動生成する"""
    import secrets
    import string

    random_num = secrets.randbelow(9000) + 1000
    login_id = f"user_{random_num}"
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{name}.", login_id, password


# --- データロードとレート計算の実行 ---
df_games, df_members, df_logs = load_data()
player_ratings, rating_history = calculate_all_ratings(df_games, df_members)

# 最新レートをマスタへ反映
for n, v in player_ratings.items():
    df_members.loc[df_members["名前"] == n, "現在のレート"] = round(v, 1)

# ログイン状態の管理初期化
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_name" not in st.session_state:
    st.session_state["user_name"] = ""

# 自動ログイン（クッキーの読み込み）
if st.session_state["cookies_initialized"] and not st.session_state["logged_in"]:
    sid = st.session_state["controller"].get("saved_login_id")
    spw = st.session_state["controller"].get("saved_login_pw")
    if sid and spw:
        user = df_members[
            (df_members["ログインID"] == sid)
            & (df_members["パスワード"].astype(str) == spw)
        ]
        if not user.empty:
            st.session_state["logged_in"] = True
            st.session_state["user_name"] = str(user["名前"].values[0])

# サイドバーメニュー
menu = st.sidebar.radio("メニュー", ["お客様ページ", "スタッフ専用入力画面"])

# ==================== スタッフ専用入力画面 ====================
if menu == "スタッフ専用入力画面":
    st.header("💻 スタッフ専用・対局結果管理")
    password_input = st.text_input("管理用パスワード", type="password")

    if password_input == "admin123":
        st.success("認証されました。")
        t1, t2 = st.tabs(["📝 新規登録", "🗂️ 過去データ確認・修正"])

        with t1:
            with st.form("input_form", clear_on_submit=True):
                g_dt = st.date_input("試合日", datetime.date.today())
                p1 = st.text_input("1位")
                p2 = st.text_input("2位")
                p3 = st.text_input("3位")
                p4 = st.text_input("4位")

                if st.form_submit_button("保存・確定"):
                    if p1 and p2 and p3 and p4 and len({p1, p2, p3, p4}) == 4:
                        for p in [p1, p2, p3, p4]:
                            if p not in df_members["名前"].values:
                                web_name, rid, rpw = generate_login_info(p)

                                new_member = pd.DataFrame(
                                    [
                                        {
                                            "名前": p,
                                            "Web用表示名": web_name,
                                            "ログインID": rid,
                                            "パスワード": rpw,
                                            "初期レート": 1500.0,
                                            "現在のレート": 1500.0,
                                        }
                                    ]
                                )
                                df_members = pd.concat(
                                    [df_members, new_member], ignore_index=True
                                )
                                st.info(f"🆕 新規客: 【{p}】 ID:{rid} PW:{rpw}")

                        new_g = pd.DataFrame(
                            [
                                {
                                    "試合日": g_dt.strftime("%Y-%m-%d"),
                                    "1位": p1,
                                    "2位": p2,
                                    "3位": p3,
                                    "4位": p4,
                                }
                            ]
                        )
                        df_games = pd.concat([df_games, new_g], ignore_index=True)
                        save_excel(df_games, df_members, df_logs)
                        st.success("保存しました！")
                        st.rerun()
                    else:
                        st.error("入力が正しくありません（同名または空欄があります）。")
        with t2:
            edt_g = st.data_editor(
                df_games, num_rows="dynamic", use_container_width=True
            )
            if st.button("💾 Excelを上書き保存"):
                save_excel(edt_g, df_members, df_logs)
                st.success("上書き保存しました！")
                st.rerun()
# ==================== お客様ページ ====================
else:
    if not st.session_state["logged_in"]:
        st.subheader("🔑 プレイヤーログイン")
        uid = st.text_input("ログインID")
        upw = st.text_input("パスワード", type="password")
        rem = st.checkbox("ログイン情報を記憶する", value=True)

        if st.button("ログイン") and uid and upw:
            user = df_members[
                (df_members["ログインID"] == uid)
                & (df_members["パスワード"].astype(str) == upw)
            ]
            if not user.empty:
                # 確実に単一の文字列（配列ではない形）として名前を抽出
                uname = str(user["名前"].values[0])
                st.session_state["logged_in"] = True
                st.session_state["user_name"] = uname

                if rem and st.session_state["cookies_initialized"]:
                    st.session_state["controller"].set("saved_login_id", uid)
                    st.session_state["controller"].set("saved_login_pw", upw)

                new_l = pd.DataFrame(
                    [
                        {
                            "閲覧日時": datetime.datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "ログインID": uid,
                            "名前": uname,
                        }
                    ]
                )
                df_logs = pd.concat([df_logs, new_l], ignore_index=True)
                save_excel(df_games, df_members, df_logs)
                st.success(f"ようこそ、{uname} さん！")
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います。")
    else:
        st.sidebar.write(f"ログイン: {st.session_state['user_name']} さん")
        if st.sidebar.button("ログアウト（記憶消去）"):
            st.session_state["logged_in"] = False
            st.session_state["user_name"] = ""
            if st.session_state["cookies_initialized"]:
                st.session_state["controller"].remove("saved_login_id")
                st.session_state["controller"].remove("saved_login_pw")
            st.rerun()

        tab1, tab2 = st.tabs(["📊 マイデータ", "🏆 総合ランキング"])

        with tab1:
            my_name = st.session_state["user_name"]
            st.header(f"👤 {my_name} さんのマイページ")

            p_stats = calculate_personal_stats(df_games, my_name)

            # 現在のレート表示
            my_rate_df = df_members[df_members["名前"] == my_name]
            my_rt_val = my_rate_df["現在のレート"].values if not my_rate_df.empty else 1500.0
            st.metric(label="現在のレーティング", value=f"{my_rt_val} Rt")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🌙 月間成績")
                st.write(f"**平均着順:** {p_stats['月間平均']} 着")
                st.write(f"**トップ率:** {p_stats['月間トップ']} %")
                st.write(f"**ラス率:** {p_stats['月間ラス']} %")
                st.write(f"**着順内訳:** 1着:{p_stats['月間着順回数'][1]}回 / 2着:{p_stats['月間着順回数'][2]}回 / 3着:{p_stats['月間着順回数'][3]}回 / 4着:{p_stats['月間着順回数'][4]}回")
                st.write(f"**対戦数:** {p_stats['月間対戦数']} / 30 戦")
                if p_stats["月間対戦数"] < 30:
                    st.progress(p_stats["月間対戦数"] / 30)
                    st.caption(f"あと **{30 - p_stats['月間対戦数']}戦**")
                else:
                    st.success("🎉 月間規定打数クリア！")
            with col2:
                st.subheader("☀️ 年間成績")
                st.write(f"**平均着順:** {p_stats['年間平均']} 着")
                st.write(f"**トップ率:** {p_stats['年間トップ']} %")
                st.write(f"**ラス率:** {p_stats['年間ラス']} %")
                st.write(f"**着順内訳:** 1着:{p_stats['年間着順回数'][1]}回 / 2着:{p_stats['年間着順回数'][2]}回 / 3着:{p_stats['年間着順回数'][3]}回 / 4着:{p_stats['年間着順回数'][4]}回")
                st.write(f"**対戦数:** {p_stats['年間対戦数']} / 360 戦")
                if p_stats["年間対戦数"] < 360:
                    st.progress(p_stats["年間対戦数"] / 360)
                    st.caption(f"あと **{360 - p_stats['年間対戦数']}戦**")
                else:
                    st.success("🎉 年間規定打数クリア！")

            # 対局履歴テーブル
            st.subheader("🗂️ 直近の対局履歴（対戦相手）")
            df_hist = get_personal_history(df_games, my_name)
            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("対局履歴がありません。")

            # --- 【新機能】着順内訳の円グラフ＆スタッツ表示 ---
            st.subheader("📊 着順内訳の割合（通算）")
            
            # 全対局から本人の着順データを集計
            df_g_copy = df_games.copy()
            melted_all = []
            for r in range(1, 5):
                t = df_g_copy[[f"{r}位"]].rename(columns={f"{r}位": "名前"})
                t["着順"] = f"{r}着"
                melted_all.append(t)
            df_all_flat = pd.concat(melted_all, ignore_index=True)
            df_my_ranks = df_all_flat[df_all_flat["名前"] == my_name]

            if not df_my_ranks.empty:
                # 各着順の回数をカウント
                rank_counts = df_my_ranks["着順"].value_counts().reset_index()
                rank_counts.columns = ["着順", "回数"]
                
                # 1着〜4着の順番に固定
                rank_counts["sort"] = rank_counts["着順"].str.get(0).astype(int)
                rank_counts = rank_counts.sort_values("sort")

                # トップ率・ラス率を大きな文字で表示
                col_rate1, col_rate2 = st.columns(2)
                with col_rate1:
                    st.metric(label="🏆 通算トップ率", value=f"{top_rate:.1f} %")
                with col_rate2:
                    st.metric(label="💀 通算ラス率", value=f"{las_rate:.1f} %")
                
                # 円グラフの作成
                fig_pie = px.pie(
                    rank_counts, 
                    values="回数", 
                    names="着順", 
                    hole=0.3,
                    color="着順",
                    color_discrete_map={"1着":"#1f77b4", "2着":"#aec7e8", "3着":"#ffbb78", "4着":"#ff7f0e"}
                )
                # グラフ内の文字サイズを「18」に大きく拡大し、太字に変更
                fig_pie.update_traces(
                    textposition='inside', 
                    textinfo='percent+label',
                    textfont_size=18,
                    insidetextfont=dict(color='white', weight='bold')
                )
                # 凡例（右側の文字説明）のサイズも拡大
                fig_pie.update_layout(legend=dict(font=dict(size=14)))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("円グラフを表示するための対局データがありません。")

            # レート推移グラフ
            st.subheader("📈 レーティング推移")
            if my_name in rating_history and len(rating_history[my_name]) > 1:
                df_chart = pd.DataFrame(
                    {
                        "対戦回数": list(range(len(rating_history[my_name]))),
                        "レーティング": rating_history[my_name],
                    }
                )
                fig = px.line(
                    df_chart,
                    x="対戦回数",
                    y="レーティング",
                    title="Rt変動トレンド",
                    markers=True,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("十分な対局データがありません。")
        with tab2:
            st.header("店舗総合トップ10")
            st.write("※平均着順2.5以下の方が対象（名前は匿名化）")

            if not df_games.empty:
                df_g_all = df_games.copy()
                df_g_all["試合日"] = pd.to_datetime(df_g_all["試合日"])
                now = datetime.datetime.now()

                melted_all = []
                for r in range(1, 5):
                    t = df_g_all[["試合日", f"{r}位"]].rename(columns={f"{r}位": "名前"})
                    t["着順"] = r
                    melted_all.append(t)

                df_all_flat = pd.concat(melted_all, ignore_index=True)
                p_choice = st.radio("期間", ["月間（動的規定打数）", "年間（360戦以上）"])

                # --- 【新機能】日付に応じた月間最低打数の自動判定 ---
                if "月間" in p_choice:
                    df_f = df_all_flat[
                        (df_all_flat["試合日"].dt.year == now.year)
                        & (df_all_flat["試合日"].dt.month == now.month)
                    ]
                    # 1日〜25日は「今日の日付」、26日以降は「30」にする
                    if now.day <= 25:
                        min_g = now.day
                        st.caption(f"📢 本日({now.day}日)のランキング掲載条件: **{min_g}半荘以上**")
                    else:
                        min_g = 30
                        st.caption(f"📢 月末のランキング掲載条件: **30半荘以上**")
                else:
                    df_f = df_all_flat[df_all_flat["試合日"].dt.year == now.year]
                    min_g = 360
                    st.caption(f"📢 年間のランキング掲載条件: **360半荘以上**")

                if not df_f.empty:
                    stats = (
                        df_f.groupby("名前")["着順"]
                        .agg(対戦数="count", 平均着順="mean")
                        .reset_index()
                    )
                    ranking = stats[
                        (stats["対戦数"] >= min_g) & (stats["平均着順"] <= 2.5)
                    ]

                    if not ranking.empty:
                        rk = ranking.merge(
                            df_members[["名前", "Web用表示名", "現在のレート"]],
                            on="名前",
                        )
                        rk_sorted = rk.sort_values(by="平均着順").head(10).copy()
                        rk_sorted.insert(0, "順位", range(1, len(rk_sorted) + 1))

                        st.dataframe(
                            rk_sorted[
                                [
                                    "順位",
                                    "Web用表示名",
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
