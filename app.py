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
    """【強化版】最優先でGitHubから最新データを取得し、セッション内で保持する"""
    if "db_games" not in st.session_state:
        st.session_state["db_games"] = pd.DataFrame(columns=["試合日", "1位", "2位", "3位", "4位"])
    if "db_members" not in st.session_state:
        st.session_state["db_members"] = pd.DataFrame([{
            "名前": "管理者", "Web用表示名": "管.", "ログインID": "admin001", "パスワード": "password", "初期レート": 1500.0, "現在のレート": 1500.0
        }])
    if "db_logs" not in st.session_state:
        st.session_state["db_logs"] = pd.DataFrame(columns=["閲覧日時", "ログインID", "名前"])

    if st.session_state.get("data_loaded_from_github", False):
        return st.session_state["db_games"], st.session_state["db_members"], st.session_state["db_logs"]

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return st.session_state["db_games"], st.session_state["db_members"], st.session_state["db_logs"]

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    res = github_api_request("GET", url)

    if res.status_code == 200:
        import base64
        res_json = res.json()
        content_b64 = res_json.get("content", "")
        st.session_state["github_sha"] = res_json.get("sha")

        if content_b64:
            try:
                raw_data = json.loads(base64.b64decode(content_b64).decode("utf-8"))
                if "games" in raw_data: st.session_state["db_games"] = pd.DataFrame(raw_data["games"])
                if "members" in raw_data: st.session_state["db_members"] = pd.DataFrame(raw_data["members"])
                if "logs" in raw_data: st.session_state["db_logs"] = pd.DataFrame(raw_data["logs"])
                st.session_state["data_loaded_from_github"] = True
            except Exception:
                pass
    elif res.status_code == 404:
        st.session_state["data_loaded_from_github"] = True

    return st.session_state["db_games"], st.session_state["db_members"], st.session_state["db_logs"]


def save_excel(df_g, df_m, df_l):
    """【強化版】最新データをメモリに保存し、即座にGitHubへ確実コミットする"""
    import base64
    st.session_state["db_games"] = df_g
    st.session_state["db_members"] = df_m
    st.session_state["db_logs"] = df_l

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    data_payload = {
        "games": df_g.to_dict(orient="records"),
        "members": df_m.to_dict(orient="records"),
        "logs": df_l.to_dict(orient="records"),
    }
    json_str = json.dumps(data_payload, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    res_get = github_api_request("GET", url)
    sha = res_get.json().get("sha") if res_get.status_code == 200 else st.session_state.get("github_sha")

    commit_data = {
        "message": f"📊 雀荘データ自動更新 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
        "content": content_b64,
    }
    if sha:
        commit_data["sha"]
