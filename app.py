from datetime import datetime
from pathlib import Path
import random
import time
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="人脸刺激评分与数据收集系统",
    page_icon="🧠",
    layout="centered",
)

BASE_DIR = Path(__file__).parent
STIMULI_DIR = BASE_DIR / "stimuli"

# ==================== 指导语配置（可按需修改） ====================
INSTRUCTION_TITLE = "实验指导语"
INSTRUCTION_TEXT = """
欢迎参与本次人脸图片评分任务！

1. **开始前准备**：请先填写您的**被试编号**（如 `P01`），并确认已阅读本指导语。
2. **评分作答**：进入任务后，屏幕将逐张呈现人脸图片。请结合您的第一反应，在量表上对当前图片进行评分；系统会自动记录每张图片的作答耗时（反应时，单位：秒）。
3. **提交与进度**：每张图片评分完成后，点击**「提交并下一张」**进入下一张图片；顶部进度条会显示当前完成进度。
4. **数据导出**：全部图片评分完成后，页面将汇总本次作答记录并提供 **CSV 文件下载**。由于 Streamlit 云端容器在休眠或重启时不会长期保留本地文件，请在完成页**务必点击下载 CSV 文件**并妥善保存。
"""

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_stimuli_files() -> list[Path]:
    """读取 stimuli/ 目录下所有支持格式的图片文件。"""
    if not STIMULI_DIR.exists():
        return []
    return sorted(
        [p for p in STIMULI_DIR.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
        key=lambda p: p.name.lower(),
    )


def sanitize_filename_part(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text.strip())
    return cleaned or "participant"


def build_records_dataframe(records: list[dict]) -> pd.DataFrame:
    columns = [
        "timestamp",
        "participant_id",
        "trial_order",
        "shuffled",
        "image_name",
        "valence_1_to_7",
        "trustworthiness_1_to_7",
        "attractiveness_1_to_7",
        "rt_sec",
        "remark",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


# ==================== 会话状态初始化 ====================
if "stage" not in st.session_state:
    st.session_state.stage = "instruction"  # instruction | rating | finished
if "participant_id" not in st.session_state:
    st.session_state.participant_id = ""
if "shuffle_order" not in st.session_state:
    st.session_state.shuffle_order = True
if "ordered_files" not in st.session_state:
    st.session_state.ordered_files = []
if "trial_idx" not in st.session_state:
    st.session_state.trial_idx = 0
if "records" not in st.session_state:
    st.session_state.records = []
if "trial_start_ts" not in st.session_state:
    st.session_state.trial_start_ts = None

stimuli_files = load_stimuli_files()

# ==================== 阶段 1：指导语与被试登记 ====================
if st.session_state.stage == "instruction":
    st.title("🧠 人脸图片评分任务")
    st.subheader(INSTRUCTION_TITLE)
    st.markdown(INSTRUCTION_TEXT)

    if len(stimuli_files) == 0:
        st.error(
            f"当前在 `{STIMULI_DIR.name}/` 目录中未检测到图片（支持 jpg/jpeg/png/webp/bmp）。"
            "请将图片放入仓库的 `stimuli/` 文件夹并推送至 GitHub 后刷新页面。"
        )
    else:
        st.info(f"已检测到 **{len(stimuli_files)}** 张待评分图片。")

    with st.form("start_form"):
        pid_input = st.text_input(
            "被试编号 *",
            value=st.session_state.participant_id,
            placeholder="例如：P01",
        )
        shuffle_opt = st.checkbox(
            "随机呈现图片顺序（推荐）",
            value=st.session_state.shuffle_order,
        )
        agree_opt = st.checkbox("我已阅读上述指导语，自愿参与本次评分任务。")
        start_btn = st.form_submit_button("开始评分", type="primary", use_container_width=True)

    if start_btn:
        if not pid_input.strip():
            st.warning("请先填写「被试编号」。")
        elif not agree_opt:
            st.warning("请先勾选确认已阅读指导语。")
        elif len(stimuli_files) == 0:
            st.error("没有可用图片，无法开始任务。")
        else:
            files_to_run = list(stimuli_files)
            if shuffle_opt:
                random.shuffle(files_to_run)
            st.session_state.participant_id = pid_input.strip()
            st.session_state.shuffle_order = shuffle_opt
            st.session_state.ordered_files = files_to_run
            st.session_state.trial_idx = 0
            st.session_state.records = []
            st.session_state.stage = "rating"
            st.session_state.trial_start_ts = time.time()
            st.rerun()

# ==================== 阶段 2：逐张图片评分与数据收集 ====================
elif st.session_state.stage == "rating":
    files_to_run = st.session_state.ordered_files
    total = len(files_to_run)
    idx = st.session_state.trial_idx

    if st.session_state.trial_start_ts is None:
        st.session_state.trial_start_ts = time.time()

    st.progress(
        idx / total,
        text=f"被试编号：{st.session_state.participant_id} | 进度：{idx + 1} / {total}",
    )
    st.caption("请根据指导语对当前人脸图片进行评分（1 = 非常低/消极，7 = 非常高/积极）：")

    current_file = files_to_run[idx]
    st.image(str(current_file), use_container_width=True)

    valence = st.slider(
        "情绪效价（1 = 非常消极，7 = 非常积极）",
        min_value=1,
        max_value=7,
        value=4,
        key=f"valence_{idx}",
    )
    trustworthiness = st.slider(
        "可信度（1 = 极不可信，7 = 极为可信）",
        min_value=1,
        max_value=7,
        value=4,
        key=f"trust_{idx}",
    )
    attractiveness = st.slider(
        "吸引力（1 = 极低，7 = 极高）",
        min_value=1,
        max_value=7,
        value=4,
        key=f"attr_{idx}",
    )
    remark = st.text_input(
        "补充说明（可选）",
        key=f"remark_{idx}",
        placeholder="如有异常情况或备注可在此填写",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("提交并下一张", type="primary", use_container_width=True):
            rt_sec = round(time.time() - st.session_state.trial_start_ts, 3)
            st.session_state.records.append(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "participant_id": st.session_state.participant_id,
                    "trial_order": idx + 1,
                    "shuffled": st.session_state.shuffle_order,
                    "image_name": current_file.name,
                    "valence_1_to_7": int(valence),
                    "trustworthiness_1_to_7": int(trustworthiness),
                    "attractiveness_1_to_7": int(attractiveness),
                    "rt_sec": rt_sec,
                    "remark": remark.strip(),
                }
            )
            if idx + 1 < total:
                st.session_state.trial_idx += 1
                st.session_state.trial_start_ts = time.time()
            else:
                st.session_state.stage = "finished"
                st.session_state.trial_start_ts = None
            st.rerun()

    with col2:
        if st.button("返回指导语", use_container_width=True):
            st.session_state.stage = "instruction"
            st.session_state.trial_start_ts = None
            st.rerun()

# ==================== 阶段 3：完成汇总与 CSV 导出 ====================
elif st.session_state.stage == "finished":
    st.title("✅ 评分任务已完成")
    df_result = build_records_dataframe(st.session_state.records)
    st.success(
        f"感谢被试 **{st.session_state.participant_id}** 完成全部 **{len(df_result)}** 张图片的评分！"
    )

    st.dataframe(df_result, use_container_width=True)

    csv_bytes = df_result.to_csv(index=False).encode("utf-8-sig")
    safe_pid = sanitize_filename_part(st.session_state.participant_id)
    ts_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"face_ratings_{safe_pid}_{ts_label}.csv"

    st.download_button(
        label="📥 下载本次评分数据（CSV）",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    if st.button("录入下一位被试", use_container_width=True):
        st.session_state.stage = "instruction"
        st.session_state.participant_id = ""
        st.session_state.ordered_files = []
        st.session_state.trial_idx = 0
        st.session_state.records = []
        st.session_state.trial_start_ts = None
        st.rerun()
