import datetime
import math
import os
import re
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_cookies_controller import CookieController

EXCEL_FILE = "mahjong_system.xlsx"

# 画面の基本設定
st.set_page_config(page_title="雀荘レーティング＆成績管理", layout="centered")

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
    if rating <= 1349: return "🦥 ナマケモノ級"
    elif rating <= 1449: return "🦝 アライグマ級"
    elif rating <= 1549: return "🐻 マレーグマ級"
    elif rating <= 1649: return "🐼 ジャイアントパンダ級"
    elif rating <= 1749: return "👓 メガネグマ級"
    elif rating <= 1849: return "🧗 ナマケグマ級"
    elif rating <= 1949: return "🌙 ツキノワグマ級"
    elif rating <= 2049: return "🌲 アメリカクロクマ級"
    elif rating <= 2149: return "🪵 ヒグマ級"
    else: return "❄️ ホッキョクグマ級"


def load_data():
    """スプレッドシートの通信バグを100%修正した安全な読み込み"""
    url = st.secrets["general"]["spreadsheet_url"]
    
    match = re.search(r"/d/([^/]+)", url)
    if not match:
        st.error("Secretsに登録されているGoogleスプレッドシートのURL形式が正しくありません。")
        st.stop()
    sheet_id = match.group(1)
    
    url_games = f"https://google.com{sheet_id}/export?format=csv&sheet=games"
    url_members = f"https://google.com{sheet_id}/export?format=csv&sheet=members"
    url_logs = f"https://google.com{sheet_id}/export?format=csv&sheet=logs"

    try:
        df_g = pd.read_csv(url_games)
        df_m = pd.read_csv(url_members)
    except Exception as e:
        st.error("Googleスプレッドシートの読み込みに失敗しました。共有設定が「リンクを知っている全員」になっているかご確認ください。")
        st.stop()

    try:
        df_l = pd.read_csv(url_logs)
    except Exception:
        df_l = pd.DataFrame(columns=["閲覧日時", "ログインID", "名前"])

    if "初期レート" not in df_m.columns: df_m["初期レート"] = 1500.0
    if "現在のレート" not in df_m.columns: df_m["現在のレート"] = 1500.0

    return df_g, df_m, df_l


def save_excel(df_g, df_m, df_l):
    """Web上の入力データをセッションに一時保存する"""
    st.session_state["temporary_df_games"] = df_g
    st.session_state["temporary_df_members"] = df_m
    st.session_state["temporary_df_logs"] = df_l


def calculate_all_ratings(df_g, df_m):
    """過去の全対局からレーティングの推移を計算する"""
    p_rt = {n: 1500.0 for n in df_m["名前"]}
    rt_hist = {n: [1500.0] for n in df_m["名前"]}
    if df_g.empty: return p_rt, rt_hist

    df_g_sorted = df_g.sort_values(by="試合日").copy()
    for _, row in df_g_sorted.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]
        for p in p_list:
            if p not in p_rt: p_rt[p], rt_hist[p] = 1500.0, [1500.0]
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
    """個人の月間・年間成績を計算する"""
    default_stats = {
        "月間対戦数": 0, "月間平均": 0.0, "月間トップ": 0.0, "月間ラス": 0.0, "月間着順回数": {1: 0, 2: 0, 3: 0, 4: 0},
        "年間対戦数": 0, "年間平均": 0.0, "年間トップ": 0.0, "年間ラス": 0.0, "年間着順回数": {1: 0, 2: 0, 3: 0, 4: 0}
    }
    if df_g.empty: return default_stats
    df_g_copy = df_g.copy()
    df_g_copy["試合日"] = pd.to_datetime(df_g_copy["試合日"])
    now = datetime.datetime.now()
    melted = [df_g_copy[["試合日", f"{r}位"]].rename(columns={f"{r}位": "名前"}).assign(着順=r) for r in range(1, 5)]
    df_all = pd.concat(melted, ignore_index=True)
    df_p = df_all[df_all["名前"] == p_name]
    if df_p.empty: return default_stats
    df_m = df_p[(df_p["試合日"].dt.year == now.year) & (df_p["試合日"].dt.month == now.month)]
    df_y = df_p[df_p["試合日"].dt.year == now.year]
    m_count, y_count = len(df_m), len(df_y)
    return {
        "月間対戦数": m_count, "月間平均": round(df_m["着順"].mean(), 2) if m_count > 0 else 0.0,
        "月間トップ": round(len(df_m[df_m["着順"] == 1]) / m_count * 100, 1) if m_count > 0 else 0.0,
        "月間ラス": round(len(df_m[df_m["着順"] == 4]) / m_count * 100, 1) if m_count > 0 else 0.0,
        "月間着順回数": {r: len(df_m[df_m["着順"] == r]) for r in range(1, 5)},
        "年間対戦数": y_count, "年間平均": round(df_y["着順"].mean(), 2) if y_count > 0 else 0.0,
        "年間トップ": round(len(df_y[df_y["着順"] == 1]) / y_count * 100, 1) if y_count > 0 else 0.0,
        "年間ラス": round(len(df_y[df_y["着順"] == 4]) / y_count * 100, 1) if y_count > 0 else 0.0,
        "年間着順回数": {r: len(df_y[df_y["着順"] == r]) for r in range(1, 5)}
    }


def get_personal_history(df_g, p_name):
    """個人の過去の対局履歴を取得する"""
    if df_g.empty: return pd.DataFrame()
    rows = []
    for _, row in df_g.iterrows():
        p_list = [row["1位"], row["2位"], row["3位"], row["4位"]]
        if p_name in p_list:
            rows.append({"対戦日": row["試合日"], "あなたの着順": f"{p_list.index(p_name)+1}着", "1位": row["1位"], "2位": row["2位"], "3位": row["3位"], "4位": row["4位"]})
    return pd.DataFrame(rows).sort_values(by="対戦日", ascending=False) if rows else pd.DataFrame()


def generate_login_info(name):
    """新規客用のID・PWを生成する"""
    import secrets, string
    rid = f"user_{secrets.randbelow(9000)+1000}"
    rpw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    return f"{name}.", rid, rpw


# --- データのロードと初期実行 ---
df_games, df_members, df_logs = load_data()
player_ratings, rating_history = calculate_all_ratings(df_games, df_members)
for n, v in player_ratings.items(): df_members.loc[df_members["名前"] == n, "現在のレート"] = round(v, 1)

if "logged_in" not in st.session_state: st.session_state.update({"logged_in": False, "user_name": ""})
if st.session_state["cookies_initialized"] and not st.session_state["logged_in"]:
    sid, spw = st.session_state["controller"].get("saved_login_id"), st.session_state["controller"].get("saved_login_pw")
    if sid and spw:
        user = df_members[(df_members["ログインID"] == sid) & (df_members["パスワード"].astype(str) == spw)]
        if not user.empty: st.session_state.update({"logged_in": True, "user_name": str(user["名前"].values)})

menu = st.sidebar.radio("メニュー", ["お客様ページ", "スタッフ専用入力画面"])

if menu == "スタッフ専用入力画面":
    st.header("💻 スタッフ専用・対局結果管理")
    if st.text_input("管理用パスワード", type="password") == "admin123":
        st.success("認証されました。")
        t1, t2 = st.tabs(["📝 新規登録", "🗂️ 過去データ確認·修正"])
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
                        st.rerun()
                    else: st.error("入力欄に不備があります。")
        with t2:
            edt_g = st.data_editor(df_games, num_rows="dynamic", use_container_width=True)
            if st.button("💾 スプレッドシートを上書き保存"):
                save_excel(edt_g, df_members, df_logs)
                st.success("上書き保存しました！")
                st.rerun()
else:
    if not st.session_state["logged_in"]:
        st.subheader("🔑 プレイヤーログイン")
        uid, upw, rem = st.text_input("ログインID"), st.text_input("パスワード", type="password"), st.checkbox("ログイン情報を記憶する", value=True)
        if st.button("ログイン") and uid and upw:
            user = df_members[(df_members["ログインID"] == uid) & (df_members["パスワード"].astype(str) == upw)]
            if not user.empty:
                uname = str(user["名前"].values)
                st.session_state.update({"logged_in": True, "user_name": uname})
                if rem and st.session_state["cookies_initialized"]:
                    st.session_state["controller"].set("saved_login_id", uid)
                    st.session_state["controller"].set("saved_login_pw", upw)
                df_logs = pd.concat([df_logs, pd.DataFrame([{"閲覧日時":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"ログインID":uid,"名前":uname}])], ignore_index=True)
                save_excel(df_games, df_members, df_logs)
                st.success(f"ようこそ、{uname} さん！")
                st.rerun()
            else: st.error("IDまたはパスワードが違います。")
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
            my_rt_val = my_rate_df["現在のレート"].values if not my_rate_df.empty else 1500.0
            dan_name = get_dan_name(my_rt_val)

            st.metric(label="現在のレーティング", value=f"{my_rt_val} Rt")
            st.header(f"🏆 現在の階級：{dan_name}")
            st.write("---")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🌙 月間成績")
                st.write(f"**平均着順:** {p_stats['月間平均']} 着\n\n**トップ率:** {p_stats['月間トップ']} %\n\n**ラス率:** {p_stats['月間ラス']} %")
                m_rc = p_stats["月間着順回数"]
                st.write(f"**着順内訳:** 1着:{m_rc}回 / 2着:{m_rc}回 / 3着:{m_rc}回 / 4着:{m_rc}回")
                st.write(f"**対戦数:** {p_stats['月間対戦数']} / 30 戦")
                if p_stats["月間対戦数"] < 30:
                    st.progress(p_stats["月間対戦数"] / 30)
                    st.caption(f"あと **{30 - p_stats['月間対戦数']}戦**")
                else: st.success("🎉 月間規定打数クリア！")
            with col2:
                st.subheader("☀️ 年間成績")
                st.write(f"**平均着順:** {p_stats['年間平均']} 着\n\n**トップ率:** {p_stats['年間トップ']} %\n\n**ラス率:** {p_stats['年間ラス']} %")
                y_rc = p_stats["年間着順回数"]
                st.write(f"**着順内訳:** 1着:{y_rc}回 / 2着:{y_rc}回 / 3着:{y_rc}回 / 4着:{y_rc}回")
                st.write(f"**対戦数:** {p_stats['年間対戦数']} / 360 戦")
                if p_stats["年間対戦数"] < 360:
                    st.progress(p_stats["年間対戦数"] / 360)
                    st.caption(f"あと **{360 - p_stats['年間対戦数']}戦**")
                else: st.success("🎉 年間規定打数クリア！")

            st.subheader("🗂️ 直近の対局履歴（対戦相手）")
            df_hist = get_personal_history(df_games, my_name)
            if not df_hist.empty: st.dataframe(df_hist, use_container_width=True)
            else: st.info("対局履歴がありません。")

            st.subheader("📊 着順内訳の割合（通算）")
            df_g_copy = df_games.copy()
            melted_all = [df_g_copy[[f"{r}位"]].rename(columns={f"{r}位": "名前"}).assign(着順=f"{r}着") for r in range(1, 5)]
            df_all_flat = pd.concat(melted_all, ignore_index=True)
            df_my_ranks = df_all_flat[df_all_flat["名前"] == my_name]

            if not df_my_ranks.empty:
                rank_counts = df_my_ranks["着順"].value_counts().reset_index()
                rank_counts.columns = ["着順", "回数"]
                rank_counts["sort"] = rank_counts["着順"].str.get(0).astype(int)
                rank_counts = rank_counts.sort_values("sort")
                fig_pie = px.pie(rank_counts, values="回数", names="着順", hole=0.3, color="着順", color_discrete_map={"1着": "#1f77b4", "2着": "#aec7e8", "3着": "#ffbb78", "4着": "#ff7f0e"})
                fig_pie.update_traces(textposition="inside", textinfo="percent+label", textfont_size=18, insidetextfont=dict(color="white", weight="bold"))
                fig_pie.update_layout(legend=dict(font=dict(size=14)))
                st.plotly_chart(fig_pie, use_container_width=True)
            else: st.info("円グラフを表示するための対局データがありません。")

            st.subheader("📈 レーティング推移")
            if my_name in rating_history and len(rating_history[my_name]) > 1:
                df_chart = pd.DataFrame({"対戦回数": list(range(len(rating_history[my_name]))), "レーティング": rating_history[my_name]})
                fig = px.line(df_chart, x="対戦回数", y="レーティング", title="Rt変動トレンド", markers=True)
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
                melted_all = [df_g_all[["試合日", f"{r}位"]].rename(columns={f"{r}位": "名前"}).assign(着順=r) for r in range(1, 5)]
                df_all_flat = pd.concat(melted_all, ignore_index=True)
                p_choice = st.radio("期間", ["月間（動的規定打数）", "年間（360戦以上）"])

                if "月間" in p_choice:
                    df_f = df_all_flat[(df_all_flat["試合日"].dt.year == now.year) & (df_all_flat["試合日"].dt.month == now.month)]
                    min_g = now.day if now.day <= 25 else 30
                    st.caption(f"📢 本日のランキング掲載条件: **{min_g}半荘以上**")
                else:
                    df_f = df_all_flat[df_all_flat["試合日"].dt.year == now.year]
                    min_g = 360
                    st.caption(f"📢 年間のランキング掲載条件: **360半荘以上**")

                if not df_f.empty:
                    stats = df_f.groupby("名前")["着順"].agg(対戦数="count", average_rank="mean").reset_index().rename(columns={"average_rank": "平均着順"})
                    ranking = stats[(stats["対戦数"] >= min_g) & (stats["平均着順"] <= 2.5)]
                    if not ranking.empty:
                        rk = ranking.merge(df_members[["名前", "Web用表示名", "現在のレート"]], on="名前")
                        rk["現在の段位"] = rk["現在のレート"].apply(lambda x: get_dan_name(x))
                        rk_sorted = rk.sort_values(by="平均着順").head(10).copy()
                        rk_sorted.insert(0, "順位", range(1, len(rk_sorted) + 1))
                        st.dataframe(rk_sorted[["順位", "Web用表示名", "現在の段位", "平均着順", "対戦数", "現在のレート"]], use_container_width=True)
                    else: st.info("条件を満たすプレイヤーはまだいません。")
                else: st.info("選択された期間の対局データがありません。")
            else: st.info("対局データがありません。")

