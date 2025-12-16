import webview
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import re
import json

# =======================
# 最终修复版爬虫函数
# =======================
def get_markdown_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except Exception as e:
        return f"# 错误\n无法加载页面: {e}"

    soup = BeautifulSoup(response.text, 'html.parser')
    content = soup.find('div', id='PostContent')
    if not content:
        content = soup.find('div', class_='entry-content') or soup.body
    # 1. 清理显示层
    for visual_tag in content.find_all(class_=['MathJax_Preview', 'MathJax_Display', 'MathJax', 'mjx-eqn']):
        visual_tag.decompose()
    formulas = {}
    # 2. 提取行间公式
    for i, script in enumerate(content.find_all('script', type='math/tex; mode=display')):
        latex = script.string if script.string else ""
        placeholder = f"MATHBLOCKPLACEHOLDER{i}"
        formulas[placeholder] = f"\n\n$$ {latex} $$\n\n"
        script.replace_with(placeholder)
    # 3. 提取行内公式
    for i, script in enumerate(content.find_all('script', type='math/tex')):
        latex = script.string if script.string else ""
        placeholder = f"MATHINLINEPLACEHOLDER{i}"
        formulas[placeholder] = f"${latex}$"
        script.replace_with(placeholder)
    # 4. 清理其他标签
    for tag in content.find_all(['style', 'script']):
        tag.decompose()
    # 5. 放心地转换为 Markdown
    text = md(str(content), heading_style="atx", bullets="-")
    # 6. 【关键调整】先还原公式，让文本里包含 LaTeX 源码
    for key, val in formulas.items():
        text = text.replace(key, val)
    # 7. 【核心生效位置】在此处执行正则替换
    # 作用：将 \[5pt] 这种带参数的换行，强行替换为标准的 \\ (双反斜杠)
    # 这样既修复了 MathJax 报错，也处理了转义问题
    text = re.sub(r'\\\[(\s*\d+[a-z]{2}\s*)\]', r'\\\\', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# =======================
# 2. PyWebview API 接口
# =======================
import logging
class Api:
    def fetch_url(self, url):
        # 不要用 print，或者确保 print 不会阻塞
        # print(f"正在抓取: {url}") 
        logging.warning(f"开始抓取: {url}") 
        return get_markdown_content(url)

# =======================
# 3. 前端界面 (HTML/JS/CSS)
# =======================
html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Markdown 爬虫编辑器</title>
    <!-- 引入 Marked 解析 Markdown -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <!-- 引入 MathJax 解析公式 -->
    <script>
    MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
      },
      svg: { fontCache: 'global' }
    };
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    
    <style>
        body { margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; font-family: sans-serif; overflow: hidden; }
        
        /* 顶部工具栏 */
        .toolbar { padding: 10px; background: #f0f0f0; border-bottom: 1px solid #ccc; display: flex; gap: 10px; }
        .toolbar input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        .toolbar button { padding: 8px 15px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .toolbar button:hover { background: #0056b3; }
        .toolbar button:disabled { background: #ccc; }

        /* 主体分栏 */
        .main { flex: 1; display: flex; overflow: hidden; }
        
        /* 编辑区 */
        .editor-container { width: 50%; border-right: 1px solid #ccc; display: flex; flex-direction: column; }
        textarea { width: 100%; height: 100%; border: none; padding: 15px; font-family: monospace; font-size: 14px; resize: none; background: #282c34; color: #abb2bf; outline: none; box-sizing: border-box; }
        
        /* 预览区 */
        .preview-container { width: 50%; padding: 20px; overflow-y: auto; background: white; }
        
        /* 简单的 Markdown 样式优化 */
        .preview-container img { max-width: 100%; }
        .preview-container blockquote { border-left: 4px solid #ccc; margin: 0; padding-left: 10px; color: #666; }
        .preview-container pre { background: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto;}
    </style>
</head>
<body>

    <div class="toolbar">
        <input type="text" id="urlInput" value="https://kexue.fm/archives/11459" placeholder="输入文章 URL">
        <button id="fetchBtn" onclick="startScrape()">抓取内容</button>
    </div>

    <div class="main">
        <div class="editor-container">
            <textarea id="editor" placeholder="Markdown 内容将显示在这里..."></textarea>
        </div>
        <div class="preview-container" id="preview">
            <!-- 渲染结果 -->
        </div>
    </div>

    <script>
        const editor = document.getElementById('editor');
        const preview = document.getElementById('preview');
        const fetchBtn = document.getElementById('fetchBtn');

        // 监听输入，实时渲染
        editor.addEventListener('input', function() {
            renderMarkdown(this.value);
        });

        // 核心渲染逻辑
        function renderMarkdown(text) {
            // 1. 将 Markdown 转 HTML
            const html = marked.parse(text);
            preview.innerHTML = html;
            
            // 2. 触发 MathJax 渲染 (对于动态内容需要重新 typeset)
            if (window.MathJax) {
                if (MathJax.texReset) {
                    MathJax.texReset();
                }
                MathJax.typesetPromise([preview]).catch((err) => console.log(err));
            }
        }

        // 调用 Python 爬虫
        function startScrape() {
            const url = document.getElementById('urlInput').value;
            if(!url) return;

            fetchBtn.innerText = "加载中...";
            fetchBtn.disabled = true;

            // 调用 Python 后端 API
            pywebview.api.fetch_url(url).then(function(response) {
                // 将结果填入编辑器
                editor.value = response;
                // 触发渲染
                renderMarkdown(response);
                
                fetchBtn.innerText = "抓取内容";
                fetchBtn.disabled = false;
            }).catch(function(err) {
                alert("抓取失败: " + err);
                fetchBtn.innerText = "抓取内容";
                fetchBtn.disabled = false;
            });
        }
    </script>
</body>
</html>
"""

# =======================
# 4. 启动程序
# =======================
if __name__ == '__main__':
    api = Api()
    window = webview.create_window(
        title='Markdown 爬取与科学公式渲染器', 
        html=html_content, 
        js_api=api,
        width=1200, 
        height=800
    )
    webview.start(debug=False) # debug=True 允许右键审查元素
