from datetime import datetime
from pathlib import Path
import random
import time
import pandas as pd
from PIL import Image, UnidentifiedImageError
import streamlit as st

st.set_page_config(
    page_title="面孔评分任务",
    page_icon="🧠",
    layout="centered",
)

BASE_DIR = Path(__file__).parent
STIMULI_DIR = BASE_DIR / "stimuli"

# ==================== 严格参照《工作簿1.xlsx》的指导语与等级 ====================
OPENING_INSTRUCTION = (
    "接下来进行面孔评分。每张面孔需要分别评价：愉悦程度、平静或激动程度，"
    "以及表情类别。请根据自己的感受，使用键盘上方数字键作答。"
    "每个页面按一次数字键即可继续。按空格键开始。"
)

FLOW_NOTE = "流程：先呈现指导语，让进行1-9的这个评分，然后对面孔进行1-5的评分。"

PLEASURE_PROMPT = "这张面孔让你感到多愉快？"
PLEASURE_LEVELS = {
    1: "1=非常不愉快",
    2: "2",
    3: "3",
    4: "4",
    5: "5=中间",
    6: "6",
    7: "7",
    8: "8",
    9: "9=非常愉快",
}
PLEASURE_FOOTER_HINT = "请按键盘上方的1-9数字键评分"

AROUSAL_PROMPT = "这张面孔让你感到多平静或激动？"
# 注：严格按表格原文保留“1=非常评价”，如需改为“1=非常平静”可在此处修改
AROUSAL_LEVELS = {
    1: "1=非常评价",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9=非常激动",
}
AROUSAL_FOOTER_HINT = "请按键盘上方的1-9数字键评分"

CATEGORY_HEADER = "评分："
CATEGORY_LEVELS = {
    1: "1=中性",
    2: "2=愤怒",
    3: "3=厌恶",
    4: "4=恐惧",
    5: "5=悲伤",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def load_stimuli_files() -> tuple[list[Path], list[str]]:
    """读取 stimuli/ 目录下所有可正常解码的图片文件，并返回无效文件列表。"""
    if not STIMULI_DIR.exists():
        return [], []

    valid_files: list[Path] = []
    invalid_names: list[str] = []

    for p in sorted(STIMULI_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not (p.is_file() and p.suffix.lower() in IMAGE_EXTS):
            continue
        try:
            with Image.open(p) as img:
                img.verify()
            valid_files.append(p)
        except (UnidentifiedImageError, OSError, Exception):
            invalid_names.append(p.name)

    return valid_files, invalid_names


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
        "pleasure_1_to_9",
        "arousal_1_to_9",
        "emotion_category_1_to_5",
        "emotion_category_label",
        "rt_1_to_9_sec",
        "rt_1_to_5_sec",
        "rt_total_sec",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


# ==================== 会话状态初始化 ====================
# stage: "instruction" -> "rating_1_9" -> "rating_1_5" -> "finished"
if "stage" not in st.session_state:
    st.session_state.stage = "instruction"
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
if "current_1_9_data" not in st.session_state:
    st.session_state.current_1_9_data = None
if "phase_start_ts" not in st.session_state:
    st.session_state.phase_start_ts = None

stimuli_files, invalid_files = load_stimuli_files()

# ==================== 阶段 1：指导语 ====================
if st.session_state.stage == "instruction":
    st.title("面孔评分")
    st.markdown(f"**{OPENING_INSTRUCTION}**")
    st.caption(FLOW_NOTE)

    st.markdown("---")
    st.markdown("**评分等级说明（严格按表格）：**")
    st.markdown(
        f"- **{PLEASURE_PROMPT}**  
"
        f"  `1=非常不愉快` · `5=中间` · `9=非常愉快`（1–9）  
"
        f"  *{PLEASURE_FOOTER_HINT}*"
    )
    st.markdown(
        f"- **{AROUSAL_PROMPT}**  
"
        f"  `1=非常评价` · `9=非常激动`（1–9）  
"
        f"  *{AROUSAL_FOOTER_HINT}*"
    )
    st.markdown(
        f"- **{CATEGORY_HEADER}**  
"
        f"  `1=中性` · `2=愤怒` · `3=厌恶` · `4=恐惧` · `5=悲伤`（1–5）"
    )

    if invalid_files:
        st.warning(
            "已自动跳过以下无法识别或损坏的图片文件："
            + "、".join(f"`{name}`" for name in invalid_files)
        )

    if len(stimuli_files) == 0:
        st.error(
            f"当前在 `{STIMULI_DIR.name}/` 目录中未检测到可用图片"
            "（支持 jpg/jpeg/png/webp/bmp/gif）。请检查仓库 `stimuli/` 目录后刷新页面。"
        )
    else:
        st.info(f"已检测到 **{len(stimuli_files)}** 张可用面孔图片。")

    with st.form("start_form"):
        pid_input = st.text_input(
            "被试编号 *",
            value=st.session_state.participant_id,
            placeholder="例如：P01",
        )
        shuffle_opt = st.checkbox(
            "随机呈现面孔顺序",
            value=st.session_state.shuffle_order,
        )
        start_btn = st.form_submit_button("开始（按空格键开始 / 点击开始）", type="primary", use_container_width=True)

    if start_btn:
        if not pid_input.strip():
            st.warning("请先填写「被试编号」。")
        elif len(stimuli_files) == 0:
            st.error("没有可用图片，无法开始。")
        else:
            files_to_run = list(stimuli_files)
            if shuffle_opt:
                random.shuffle(files_to_run)
            st.session_state.participant_id = pid_input.strip()
            st.session_state.shuffle_order = shuffle_opt
            st.session_state.ordered_files = files_to_run
            st.session_state.trial_idx = 0
            st.session_state.records = []
            st.session_state.current_1_9_data = None
            st.session_state.stage = "rating_1_9"
            st.session_state.phase_start_ts = time.time()
            st.rerun()

# ==================== 阶段 2A：先进行 1-9 评分 ====================
elif st.session_state.stage == "rating_1_9":
    files_to_run = st.session_state.ordered_files
    total = len(files_to_run)
    idx = st.session_state.trial_idx

    if st.session_state.phase_start_ts is None:
        st.session_state.phase_start_ts = time.time()

    st.progress(
        idx / total,
        text=f"被试：{st.session_state.participant_id} | 面孔 {idx + 1} / {total} | 第一步：1-9 评分",
    )

    current_file = files_to_run[idx]
    try:
        st.image(str(current_file), use_container_width=True)
    except Exception as e:
        st.error(f"当前图片 `{current_file.name}` 加载失败：{e}")
        if st.button("跳过此张并继续", type="primary"):
            st.session_state.current_1_9_data = None
            if idx + 1 < total:
                st.session_state.trial_idx += 1
                st.session_state.stage = "rating_1_9"
            else:
                st.session_state.stage = "finished"
            st.session_state.phase_start_ts = time.time()
            st.rerun()
        st.stop()

    st.markdown("---")
    # 无预设评分：index=None，必须由被试主动选择
    st.markdown(f"**{PLEASURE_PROMPT}**")
    st.caption("1=非常不愉快　　5=中间　　9=非常愉快")
    pleasure_val = st.radio(
        PLEASURE_FOOTER_HINT,
        options=list(range(1, 10)),
        index=None,
        horizontal=True,
        format_func=lambda x: PLEASURE_LEVELS[x],
        key=f"pleasure_{st.session_state.participant_id}_{idx}",
    )

    st.markdown("---")
    # 无预设评分：index=None，必须由被试主动选择
    st.markdown(f"**{AROUSAL_PROMPT}**")
    st.caption("1=非常评价　　9=非常激动")
    arousal_val = st.radio(
        AROUSAL_FOOTER_HINT,
        options=list(range(1, 10)),
        index=None,
        horizontal=True,
        format_func=lambda x: AROUSAL_LEVELS[x],
        key=f"arousal_{st.session_state.participant_id}_{idx}",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("确认 1-9 评分，进入 1-5 评分", type="primary", use_container_width=True):
            if pleasure_val is None or arousal_val is None:
                st.error("请先完成以上两项 1-9 评分（当前无预设评分，需手动选择）。")
            else:
                rt_1_9 = round(time.time() - st.session_state.phase_start_ts, 3)
                st.session_state.current_1_9_data = {
                    "pleasure_1_to_9": int(pleasure_val),
                    "arousal_1_to_9": int(arousal_val),
                    "rt_1_to_9_sec": rt_1_9,
                }
                st.session_state.stage = "rating_1_5"
                st.session_state.phase_start_ts = time.time()
                st.rerun()

    with col2:
        if st.button("返回指导语", use_container_width=True):
            st.session_state.stage = "instruction"
            st.session_state.current_1_9_data = None
            st.session_state.phase_start_ts = None
            st.rerun()

# ==================== 阶段 2B：再对面孔进行 1-5 评分 ====================
elif st.session_state.stage == "rating_1_5":
    files_to_run = st.session_state.ordered_files
    total = len(files_to_run)
    idx = st.session_state.trial_idx

    if st.session_state.phase_start_ts is None:
        st.session_state.phase_start_ts = time.time()

    st.progress(
        (idx + 0.5) / total,
        text=f"被试：{st.session_state.participant_id} | 面孔 {idx + 1} / {total} | 第二步：1-5 评分",
    )

    current_file = files_to_run[idx]
    try:
        st.image(str(current_file), use_container_width=True)
    except Exception as e:
        st.error(f"当前图片 `{current_file.name}` 加载失败：{e}")
        st.stop()

    st.markdown("---")
    # 无预设评分：index=None，必须由被试主动选择
    st.markdown(f"**{CATEGORY_HEADER}**")
    st.caption("1=中性　2=愤怒　3=厌恶　4=恐惧　5=悲伤")
    category_val = st.radio(
        "请选择 1-5 对应选项",
        options=list(range(1, 6)),
        index=None,
        horizontal=True,
        format_func=lambda x: CATEGORY_LEVELS[x],
        key=f"category_{st.session_state.participant_id}_{idx}",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        next_label = "提交并下一张" if idx + 1 < total else "提交并完成评分"
        if st.button(next_label, type="primary", use_container_width=True):
            if category_val is None:
                st.error("请先选择一项 1-5 评分（当前无预设评分，需手动选择）。")
            else:
                rt_1_5 = round(time.time() - st.session_state.phase_start_ts, 3)
                d19 = st.session_state.current_1_9_data or {}
                rt_1_9 = d19.get("rt_1_to_9_sec", 0.0)
                st.session_state.records.append(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "participant_id": st.session_state.participant_id,
                        "trial_order": idx + 1,
                        "shuffled": st.session_state.shuffle_order,
                        "image_name": current_file.name,
                        "pleasure_1_to_9": d19.get("pleasure_1_to_9"),
                        "arousal_1_to_9": d19.get("arousal_1_to_9"),
                        "emotion_category_1_to_5": int(category_val),
                        "emotion_category_label": CATEGORY_LEVELS[int(category_val)],
                        "rt_1_to_9_sec": rt_1_9,
                        "rt_1_to_5_sec": rt_1_5,
                        "rt_total_sec": round(rt_1_9 + rt_1_5, 3),
                    }
                )
                st.session_state.current_1_9_data = None
                if idx + 1 < total:
                    st.session_state.trial_idx += 1
                    st.session_state.stage = "rating_1_9"
                    st.session_state.phase_start_ts = time.time()
                else:
                    st.session_state.stage = "finished"
                    st.session_state.phase_start_ts = None
                st.rerun()

    with col2:
        if st.button("返回本张 1-9 评分", use_container_width=True):
            st.session_state.stage = "rating_1_9"
            st.session_state.phase_start_ts = time.time()
            st.rerun()

# ==================== 阶段 3：完成与 CSV 导出 ====================
elif st.session_state.stage == "finished":
    st.title("评分已完成")
    df_result = build_records_dataframe(st.session_state.records)
    st.success(
        f"被试 **{st.session_state.participant_id}** 已完成全部 **{len(df_result)}** 张面孔的评分。"
    )

    st.dataframe(df_result, use_container_width=True)

    csv_bytes = df_result.to_csv(index=False).encode("utf-8-sig")
    safe_pid = sanitize_filename_part(st.session_state.participant_id)
    ts_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"face_ratings_{safe_pid}_{ts_label}.csv"

    st.download_button(
        label="下载本次评分数据（CSV）",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    if st.button("开始下一位被试", use_container_width=True):
        st.session_state.stage = "instruction"
        st.session_state.participant_id = ""
        st.session_state.ordered_files = []
        st.session_state.trial_idx = 0
        st.session_state.records = []
        st.session_state.current_1_9_data = None
        st.session_state.phase_start_ts = None
        st.rerun()
