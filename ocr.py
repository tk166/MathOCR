import streamlit as st
from streamlit_paste_button import paste_image_button 
from streamlit_ace import st_ace
from pix2text import Pix2Text
from PIL import Image
import time
import hashlib
import re

# --- 1. 页面配置 ---
st.set_page_config(page_title="MathOCR - 图片转公式", page_icon="👀", layout="wide")
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 0rem;
            margin-top: 1rem;
        }
        /* 可选：让侧边栏也紧凑一点 */
        .css-1d391kg {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)


# --- 2. 缓存加载模型 (核心优化) ---
@st.cache_resource
def load_p2t_model():
    # 第一次运行会下载模型数据 (~400MB)
    # analyzer_config 指定模型配置，device 设为 'cpu' 或 'mps'
    # 注意：P2T 的某些组件在 MPS 上可能兼容性不如 CPU 稳，M4 CPU 足够快
    print("正在加载 Pix2Text 模型...")
    p2t = Pix2Text.from_config(device='cpu') 
    return p2t

# 加载模型 (显示个漂亮的加载条)
with st.spinner("🚀 正在初始化 AI 模型 (首次运行需下载权重)..."):
    p2t = load_p2t_model()

# --- 3. 状态管理初始化 ---
if "ocr_result" not in st.session_state:
    st.session_state.ocr_result = ""
if "editor_content" not in st.session_state:
    st.session_state.editor_content = ""
if "editor_area" not in st.session_state:
    st.session_state.editor_area = ""
# --- 4. 侧边栏：图片输入 ---
with st.sidebar:
    st.header("∑ MathOCR")
    st.subheader("")
    is_pure_formula = st.toggle("🧮 纯公式模式", value=True, help="如果截图主要是公式，开启此项可大幅提高准确率")
    uploaded_file = st.file_uploader("选择或粘贴图片", type=['png', 'jpg', 'jpeg', 'bmp'])
    st.subheader("")
    paste_result = paste_image_button(
        label="📋 点此粘贴剪贴板图片",
        background_color="#FF4B4B", # Streamlit 红色
        hover_background_color="#FF0000",
        text_color="#FFFFFF",
    )

image = None
file_id = None

# 逻辑分支 A：优先处理剪贴板图片
if paste_result.image_data is not None:
    image = paste_result.image_data
    # 给粘贴的图片一个固定的 ID，或者使用时间戳
    img_bytes = image.tobytes()
    file_id = hashlib.md5(img_bytes).hexdigest()
    last_processed_id = st.session_state.get("last_file_id", None)
    if file_id != last_processed_id:
        st.toast("✅ 已从剪贴板获取图片")

# 逻辑分支 B：处理上传的文件 (仅当没有粘贴图片时)
elif uploaded_file is not None:
    image = Image.open(uploaded_file)
    # 🟢 关键修正：这行代码必须放在这里面！
    # 只有确认 uploaded_file 不是 None，才能去读它的 name
    file_id = uploaded_file.file_id if hasattr(uploaded_file, 'file_id') else uploaded_file.name

# 逻辑分支 C：开始干活
if image is not None:
    # 1. 图片预处理 (只针对过小的图)
    w, h = image.size
    if h < 50: 
        scale = 2
        new_w = int(w * scale)
        new_h = int(h * scale)
        image = image.resize((new_w, new_h), Image.Resampling.BICUBIC) # BICUBIC 比 LANCZOS 对 OCR 更友好
        st.caption(f"⚡ 图片过小，已自动优化: {w}x{h} -> {new_w}x{new_h}")
    else:
        # 正常尺寸直接显示，不折腾
        st.caption(f"📏 图片尺寸: {w}x{h}")
    
    should_rerun = False
    
    if "last_file_id" not in st.session_state:
        should_rerun = True
    elif st.session_state.last_file_id != file_id:
        should_rerun = True

    if should_rerun:
        with st.status("🔍 正在进行 OCR 识别...", expanded=True) as status:
            start_time = time.time()
            
            # === Pix2Text 核心调用 ===
            if is_pure_formula:
                st.write("正在使用纯公式模式推理...")
                try:
                    res = p2t.recognize_formula(image)
                    if not res.startswith("$$"):
                        res = f"$$\n{res}\n$$"
                except Exception as e:
                    st.warning(f"纯公式模式出错，自动回退到通用模式: {e}")
                    res = p2t.recognize_text(image)
            else:
                res = p2t.recognize_text(image, resized_shape=1280, page_numbers=[1], threshold=0.4)
                res = re.sub(r'(?<!\n)\n(?!\n)', ' ', res)
                res = re.sub(r' +', ' ', res)
            
            time_cost = time.time() - start_time
            status.update(label=f"✅ 识别完成！耗时 {time_cost:.2f}s", state="complete", expanded=False)
            
            # 更新状态
            st.session_state.ocr_result = res
            st.session_state.editor_content = res
            st.session_state.editor_area = res
            st.session_state.last_file_id = file_id
            
            # 强制刷新页面以显示结果 (可选)
            # st.rerun() 

# --- 6. 主界面：左右分栏编辑与预览 ---
if st.session_state.editor_area:
    # st.divider()
    st.subheader("👀实时渲染")
    safe_key_suffix = file_id if file_id else "default"
    # 使用 container 给预览加个边框效果
    with st.container(height=250,border=True):
        # Streamlit 的 markdown 完美支持 $E=mc^2$ 这种 Latex 语法
        st.markdown(st.session_state.editor_area)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📝 编辑 Markdown/LaTeX")
        content = st_ace(
            value=st.session_state.editor_area,
            language="latex",
            theme="chrome", # 或 "monokai", "twilight"
            height=400,
            auto_update=True, # 👈 关键：开启实时更新
            key=f"ace_editor_{safe_key_suffix}",
            font_size=14,
            show_gutter=True, 
            show_print_margin=False,
            wrap=True
        )
        if content != st.session_state.editor_area:
            st.session_state.editor_area = content
            st.session_state.editor_content = content
            st.rerun()

    with col2:
        st.subheader("🏞️当前图片")
        st.image(image, caption="", width='stretch')

else:
    st.markdown("""
    ### 👋 欢迎使用
    
    请在左侧侧边栏 **粘贴** 或 **上传** 包含公式的图片。
    
    **功能特点：**
    - 📐 识别数学公式 (LaTeX)
    - 🇨🇳 识别中英文混合文本
    - 🖊️ 左右对照，实时修改
    """)