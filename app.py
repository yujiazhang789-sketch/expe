from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st

st.set_page_config(page_title="在线数据收集表", page_icon="📋", layout="centered")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def get_worksheet():
    """连接 Google Sheets 并返回目标工作表。"""
    gcp_info = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["sheet_url"]
    creds = Credentials.from_service_account_info(dict(gcp_info), scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(sheet_url)
    return spreadsheet.sheet1


def append_row_to_sheet(ws, row_values: list):
    headers = ["提交时间(UTC)", "编号/姓名", "评分(1-7)", "类别", "补充说明"]
    existing = ws.get_all_values()
    if len(existing) == 0:
        ws.append_row(headers, value_input_option="USER_ENTERED")
    ws.append_row(row_values, value_input_option="USER_ENTERED")


st.title("📋 线上数据收集问卷")
st.caption("填写完成后点击「提交数据」，数据将实时写入后端表格。")

if "submitted_count" not in st.session_state:
    st.session_state.submitted_count = 0

try:
    ws = get_worksheet()
    storage_ready = True
except Exception as e:
    ws = None
    storage_ready = False
    st.warning(
        "当前尚未检测到完整的 `st.secrets`（`gcp_service_account` 与 `sheet_url`）配置，"
        f"页面仍可预览界面，但暂无法写入 Google Sheets。详情：{e}"
    )

with st.form("collection_form", clear_on_submit=True):
    participant_id = st.text_input("参与者编号 / 昵称 *", placeholder="例如：P01 或 张三")
    score = st.slider("核心评分（1 = 最低，7 = 最高）", min_value=1, max_value=7, value=4)
    category = st.selectbox("样本/情境类别", ["类别 A", "类别 B", "类别 C"])
    notes = st.text_area("补充说明（可选）", placeholder="如有异常情况或备注可在此填写")
    consent = st.checkbox("我已知晓并同意本次收集的数据用于研究/分析用途 *")

    submitted = st.form_submit_button("提交数据", type="primary", use_container_width=True)

if submitted:
    if not participant_id.strip():
        st.error("请填写「参与者编号 / 昵称」。")
    elif not consent:
        st.error("请先勾选知情/确认框后再提交。")
    elif not storage_ready:
        st.error("后端表格尚未配置完成，请先在 Streamlit Secrets 中填入凭据。")
    else:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row = [now_str, participant_id.strip(), int(score), category, notes.strip()]
        try:
            append_row_to_sheet(ws, row)
            st.session_state.submitted_count += 1
            st.success(f"提交成功！本次会话已累计提交 {st.session_state.submitted_count} 条记录。")
        except Exception as e:
            st.error(f"写入失败，请稍后重试。错误信息：{e}")

# 可选：管理员查看最近记录（建议正式收集时隐藏或加密码校验）
with st.expander("查看最新已收集数据（预览）"):
    if storage_ready:
        try:
            records = ws.get_all_records()
            if records:
                st.dataframe(pd.DataFrame(records).tail(10), use_container_width=True)
            else:
                st.info("表格中暂无数据。")
        except Exception as e:
            st.error(f"读取预览失败：{e}")
