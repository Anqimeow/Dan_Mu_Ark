"""
期末复习助手 Agent (轻量版)
减负 | 诊断 | 续命 - 期末周的AI战友
适配 ModelScope 创空间 (2vCPU, 8G内存)
"""

import gradio as gr
import os
import random
import re
import time
from datetime import datetime
from openai import OpenAI

# ==================== 全局配置 ====================
CURRENT_MODEL = "qwen-plus"
MAX_CONTEXT_LENGTH = 15000  # 云端RAG上下文限制

# 全局文档存储（替代向量库）
document_store = {
    "content": "",           # 文档全文
    "source_file": "",       # 来源文件名
    "char_count": 0,         # 字符数
    "upload_time": None      # 上传时间
}

# 用户状态
user_state = {
    "energy_level": 100,
    "knowledge_mastery": 0,
    "weak_points": [],
    "current_questions": [],
    "current_question_index": 0,
    "energy_album": [],
}

# 复旦校园锚点数据
CAMPUS_ANCHORS = [
    {"id": "anchor_001", "name": "光华楼草坪", "type": "scenery",
     "description": "傍晚时分可以看到绝美落日，草坪上常有慵懒的校猫晒太阳。适合放空冥想，快速回血。",
     "tags": ["sunset", "cat", "peaceful", "outdoor"], "recoveryValue": 30, "location": "光华楼东辅楼 室外"},
    {"id": "anchor_002", "name": "旦苑一楼咖啡角", "type": "cafe",
     "description": "隐藏的咖啡小角落，有舒适的沙发和插座。咖啡性价比高，环境安静。",
     "tags": ["coffee", "quiet", "indoor", "socket"], "recoveryValue": 25, "location": "旦苑餐厅 1F"},
    {"id": "anchor_003", "name": "文科图书馆顶楼", "type": "library",
     "description": "人最少的自习区域，窗外能看到整个校园，适合需要绝对安静的深度学习。",
     "tags": ["quiet", "view", "study", "indoor"], "recoveryValue": 20, "location": "文科图书馆 5F"},
    {"id": "anchor_004", "name": "南区便利店", "type": "food",
     "description": "期末限定零食补货点！有各种能量饮料、巧克力、泡面。深夜也营业。",
     "tags": ["snacks", "energy-drink", "late-night", "shopping"], "recoveryValue": 35, "location": "南区宿舍楼下 1F"},
    {"id": "anchor_005", "name": "相辉堂后花园", "type": "scenery",
     "description": "鲜为人知的秘密花园，有小池塘和石凳，完全与世隔绝的感觉。",
     "tags": ["hidden", "peaceful", "nature", "outdoor"], "recoveryValue": 40, "location": "相辉堂 室外"},
    {"id": "anchor_006", "name": "北区食堂二楼", "type": "food",
     "description": "深夜食堂，期末周特供夜宵。麻辣烫和炒饭是续命神器。",
     "tags": ["food", "late-night", "warm", "comfort"], "recoveryValue": 35, "location": "北区食堂 2F"},
    {"id": "anchor_007", "name": "燕园操场", "type": "scenery",
     "description": "夜跑圣地，学累了来几圈，出一身汗，大脑瞬间清醒。",
     "tags": ["exercise", "outdoor", "refresh", "night"], "recoveryValue": 45, "location": "燕园 室外"},
    {"id": "anchor_008", "name": "南区猫咖", "type": "cafe",
     "description": "撸猫治愈系，十几只猫主子等你翻牌。学不进去的时候来这里充电。",
     "tags": ["cat", "cafe", "healing", "indoor"], "recoveryValue": 50, "location": "南区商业街 2F"}
]


# ==================== API 客户端 ====================

def get_real_client():
    """
    获取 OpenAI 兼容客户端（带完整错误处理）
    环境变量: xxx_KEY
    """
    try:
        # 清理代理
        os.environ['http_proxy'] = ''
        os.environ['https_proxy'] = ''
        
        # 加载环境变量 xxx_KEY
        api_key = os.getenv("xxx_KEY", "").strip()
        
        if not api_key:
            raise ValueError("未配置 API Key，请在环境变量中设置 xxx_KEY")
        
        return OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    except Exception as e:
        raise ValueError(f"创建 API 客户端失败: {str(e)}")


def chat_with_qwen(messages, temperature=0.7, max_retries=3):
    """
    调用通义千问 API（带重试和完整错误处理）
    返回: (success: bool, result: str)
    """
    for attempt in range(max_retries):
        try:
            client = get_real_client()
            response = client.chat.completions.create(
                model=CURRENT_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=2000,
            )
            return True, response.choices[0].message.content
        except ValueError as e:
            # 配置错误，不重试
            return False, f"配置错误: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            # 连接错误，重试
            if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False, f"网络连接失败，请刷新页面重试: {error_msg}"
            # 认证错误
            if "401" in error_msg or "authentication" in error_msg.lower():
                return False, "API Key 无效，请检查 xxx_KEY 配置"
            # 模型错误
            if "404" in error_msg or "model" in error_msg.lower():
                return False, f"模型 {CURRENT_MODEL} 不可用: {error_msg}"
            # 其他错误
            return False, f"API 调用失败: {error_msg}"
    
    return False, "API 调用超时，请稍后重试"


# ==================== 工具函数 ====================

def decay_energy():
    """情绪电量衰减"""
    user_state["energy_level"] = max(0, user_state["energy_level"] - 3)


def get_motivation_text(energy):
    """根据情绪电量返回温情励志文案"""
    if energy >= 80:
        return "状态超棒！感觉你现在整个人都在闪闪发光，我们要一鼓作气吗？"
    elif energy >= 60:
        return "进行得很顺利呢，你认真努力的样子真的很迷人，继续保持呀！"
    elif energy >= 40:
        return "累了吧？要不要停下来喝口水？我会一直在这里陪着你的"
    elif energy >= 20:
        return "精力快耗尽啦，抱抱你。听话，去休息一下好吗？剩下的复习思路我来帮你理清楚。"
    else:
        return "[系统预警] 指令拒绝！我不准你再熬下去了。现在、立刻、去休息！回血了咱们再战"


def get_status_display():
    """获取状态显示 - 环形仪表盘"""
    energy = user_state["energy_level"]
    mastery = user_state["knowledge_mastery"]
    
    energy_deg = int(energy * 3.6)
    mastery_deg = int(mastery * 3.6)
    
    warm_quotes = [
        "光华楼的日落，专门留给此时此刻还在努力的你。",
        "如果现在觉得累了，就去看看燕园操场上跑动的身影吧，生命力正在那里悄悄治愈呢。",
        "别担心，那些熬过的夜、写过的笔记，都会在某个清晨变成你底气十足的瞬间。",
        "本部书库里的旧书香，也曾见证过无数个像你一样闪闪发光的期末周。",
        "南区的猫可能已经睡了，但我会一直守着你的复习进度，直到你安心合上电脑。",
        "去相辉堂后的长椅坐坐吧，让大脑在老建筑的静谧里重启5分钟。"
    ]
    random_quote = random.choice(warm_quotes)
    
    if energy >= 60:
        energy_color = "#22c55e"
        energy_glow = "rgba(34, 197, 94, 0.5)"
        status_text = "身心愉悦"
        bg_gradient = "linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(99, 102, 241, 0.15) 50%, rgba(59, 130, 246, 0.1) 100%)"
        border_color = "rgba(139, 92, 246, 0.3)"
        title_gradient = "linear-gradient(135deg, #a78bfa, #818cf8)"
    elif energy >= 30:
        energy_color = "#eab308"
        energy_glow = "rgba(234, 179, 8, 0.5)"
        status_text = "有点疲惫"
        bg_gradient = "linear-gradient(135deg, rgba(251, 191, 36, 0.2) 0%, rgba(245, 158, 11, 0.15) 50%, rgba(234, 179, 8, 0.1) 100%)"
        border_color = "rgba(251, 191, 36, 0.3)"
        title_gradient = "linear-gradient(135deg, #fbbf24, #f59e0b)"
    else:
        energy_color = "#ef4444"
        energy_glow = "rgba(239, 68, 68, 0.5)"
        status_text = "急需抱抱"
        bg_gradient = "linear-gradient(135deg, rgba(251, 146, 60, 0.25) 0%, rgba(249, 115, 22, 0.2) 50%, rgba(239, 68, 68, 0.15) 100%)"
        border_color = "rgba(251, 146, 60, 0.4)"
        title_gradient = "linear-gradient(135deg, #fb923c, #f97316)"
    
    mastery_color = "#8b5cf6"
    motivation = get_motivation_text(energy)
    
    warning_html = ""
    if energy < 20:
        warning_html = '''
        <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(239, 68, 68, 0.1)); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 12px 16px; text-align: center; color: #fca5a5; font-weight: 500; margin-top: 15px;">
            警告 情绪电量告急！建议去校园补给点休息一下！
        </div>
        '''
    
    html = f'''
<div style="background: {bg_gradient}; backdrop-filter: blur(10px); border-radius: 20px; padding: 24px; border: 1px solid {border_color}; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);">
    <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.5em;">⚡</span>
            <span style="font-size: 1.3em; font-weight: 700; background: {title_gradient}; -webkit-background-clip: text; -webkit-text-fill-color: transparent;">状态监测站</span>
            <span style="margin-left: auto; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; background: {energy_color}22; color: {energy_color}; border: 1px solid {energy_color}44;">{status_text}</span>
        </div>
        <div style="font-size: 0.8em; opacity: 0.8; margin-left: 38px; color: #c4b5fd;">{random_quote}</div>
    </div>
    <div style="display: flex; justify-content: center; gap: 50px; margin: 25px 0;">
        <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
            <div style="width: 110px; height: 110px; border-radius: 50%; background: conic-gradient({energy_color} {energy_deg}deg, rgba(255,255,255,0.1) {energy_deg}deg); display: flex; align-items: center; justify-content: center; box-shadow: 0 0 25px {energy_glow};">
                <div style="width: 80px; height: 80px; border-radius: 50%; background: rgba(15, 15, 26, 0.95); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                    <span style="font-size: 2em; font-weight: 700; color: #fff;">{energy}</span>
                    <span style="font-size: 0.75em; color: #94a3b8;">%</span>
                </div>
            </div>
            <div style="font-size: 1em; color: #c4b5fd; font-weight: 600;">情绪电量</div>
        </div>
        <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
            <div style="width: 110px; height: 110px; border-radius: 50%; background: conic-gradient({mastery_color} {mastery_deg}deg, rgba(255,255,255,0.1) {mastery_deg}deg); display: flex; align-items: center; justify-content: center; box-shadow: 0 0 25px rgba(139, 92, 246, 0.4);">
                <div style="width: 80px; height: 80px; border-radius: 50%; background: rgba(15, 15, 26, 0.95); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                    <span style="font-size: 2em; font-weight: 700; color: #fff;">{mastery}</span>
                    <span style="font-size: 0.75em; color: #94a3b8;">%</span>
                </div>
            </div>
            <div style="font-size: 1em; color: #c4b5fd; font-weight: 600;">复习进度</div>
        </div>
    </div>
    <div style="text-align: center; padding: 14px 24px; background: rgba(255, 255, 255, 0.05); border-radius: 30px; color: #e2e8f0; font-size: 1.05em; margin: 20px 0 5px 0; border: 1px solid rgba(255, 255, 255, 0.1);">
        "{motivation}"
    </div>
    {warning_html}
</div>
'''
    return html


# ==================== PDF 提取 ====================

def extract_text_from_pdf(file_path):
    """从 PDF 文件提取文本"""
    import pdfplumber
    
    if not os.path.exists(file_path):
        return None, f"文件不存在: {file_path}"
    
    if os.path.getsize(file_path) == 0:
        return None, "文件为空"
    
    try:
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return None, "PDF 文件没有页面"
            
            for page in pdf.pages:
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(page_text.strip())
                except Exception:
                    continue
        
        if not text_parts:
            return None, f"未能从 {total_pages} 页中提取到文本，可能是扫描版 PDF"
        
        return "\n\n".join(text_parts), None
        
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower():
            return None, "PDF 文件已加密"
        return None, f"PDF 解析失败: {error_msg}"


# ==================== 减负功能 ====================

def analyze_document(file, content_text):
    """
    分析文档内容，提取全文存储到全局变量，生成考点地图
    轻量版：不使用向量库，直接存储全文
    """
    global document_store
    decay_energy()
    
    source_file = "文本输入"
    content = ""
    
    # 1. 获取文档内容
    if file is not None:
        try:
            file_path = file if isinstance(file, str) else (file.name if hasattr(file, 'name') else str(file))
            file_path = os.path.normpath(file_path)
            
            if not os.path.exists(file_path):
                return get_status_display(), f"文件不存在: {file_path}", ""
            
            source_file = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                content, error = extract_text_from_pdf(file_path)
                if error:
                    return get_status_display(), f"**PDF 解析失败**\n\n{error}", ""
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
        except Exception as e:
            return get_status_display(), f"**文件读取失败**\n\n{str(e)}", ""
    elif content_text:
        content = content_text
        source_file = f"文本输入_{datetime.now().strftime('%H%M%S')}"
    else:
        return get_status_display(), "请上传文件或输入文本内容", ""
    
    if len(content) < 50:
        return get_status_display(), f"内容太短（仅 {len(content)} 字符），请提供更多学习资料。", ""
    
    # 2. 存储到全局变量
    document_store["content"] = content
    document_store["source_file"] = source_file
    document_store["char_count"] = len(content)
    document_store["upload_time"] = datetime.now().isoformat()
    
    # 3. 调用 AI 生成考点地图
    analysis_text = content[:8000]  # 限制发送长度
    prompt = f"""你现在是一个专业的复旦课程领航员。请根据以下文档内容，提取出 3-5 个核心考点。

文档内容：
{analysis_text}

输出要求：
1. 使用 Markdown 表格格式
2. 必须包含 LaTeX 公式（用 $ 包裹），如果内容涉及数学、物理等学科
3. 语气要从容、专业且温柔
4. 表格列：章节/主题 | 核心概念（含公式）| 复习建议

请直接输出表格，不要有多余的解释。表头格式：
| 章节/主题 | 核心概念 | 复习建议 |
| :--- | :--- | :--- |"""

    success, result = chat_with_qwen([{"role": "user", "content": prompt}])
    
    if not success:
        heatmap = f"### 考点提取失败\n\n{result}\n\n但文档已成功存储，你可以直接在下方提问。"
    else:
        heatmap = f"""## 考点通关地图

我已经为你梳理了资料中的核心考点：

{result}"""
    
    status_msg = f"""**资料读取完成！**

来源: {source_file}
读取了: {len(content):,} 字符

你可以在下方针对内容提问，我会基于全文为你解答。"""
    
    return get_status_display(), heatmap, status_msg


def rag_query(question):
    """
    云端 RAG 问答：直接将全文 + 问题发送给大模型
    轻量版：不使用向量检索
    """
    global document_store
    decay_energy()
    
    # 检查是否有文档
    if not document_store["content"]:
        return get_status_display(), "请先上传学习资料！"
    
    if not question or len(question.strip()) < 2:
        return get_status_display(), "请输入有效的问题！"
    
    # 截取上下文（前 15000 字）
    context = document_store["content"][:MAX_CONTEXT_LENGTH]
    
    # 构建 Prompt
    prompt = f"""你是一个期末复习助手。请根据以下参考文档内容回答问题。

===参考文档===
{context}

===学生问题===
{question}

===回答要求===
1. 基于上述文档内容准确回答问题
2. 如果文档内容不足以回答，请说明需要补充哪些内容
3. 用简洁清晰的语言，帮助学生理解和记忆
4. 如果涉及公式，请使用 LaTeX 格式（$..$ 或 $$..$$）"""

    success, result = chat_with_qwen([{"role": "user", "content": prompt}])
    
    # 情绪电量低时的关怀
    care_message = ""
    if user_state["energy_level"] < 20:
        care_message = """**[温馨提示]** 虽然我找到了答案，但你的大脑已经在抗议啦。去【光华楼草坪】吹吹风好吗？

---

"""
    
    if not success:
        return get_status_display(), f"### 回答失败\n\n{result}"
    
    answer_display = f"""{care_message}## AI 回答

{result}

---
*基于 {document_store['source_file']} ({document_store['char_count']:,} 字符) 生成*"""
    
    return get_status_display(), answer_display


# ==================== 诊断功能 ====================

def start_diagnosis():
    """开始费曼诊断 - 基于文档内容生成题目"""
    global document_store
    
    if not document_store["content"]:
        return get_status_display(), "请先上传学习资料！", gr.update(choices=[], visible=False), gr.update(visible=False), gr.update(visible=False), ""
    
    # 截取内容用于出题
    content = document_store["content"][:10000]
    
    prompt = f"""你是一个专业的考试出题专家。请根据以下课程内容，生成3道不同类型的题目。

课程内容：
{content}

出题要求：
1. 所有题目必须严格基于上述课程内容中的具体知识点
2. 每道题考察不同的知识点，不要重复
3. 题目要有针对性，能检验学生对核心概念的理解

请严格按照以下格式输出，每道题占一行：

第1题（选择题）格式：
CHOICE|题目内容|选项A|选项B|选项C|正确选项(A/B/C)

第2题（填空题）格式：
FILL|题目内容（用___表示空格位置）|正确答案

第3题（简答题）格式：
SHORT|题目内容|参考答案要点

注意：
- 必须严格按照上述格式输出
- 选择题正确选项只能是A、B或C
- 直接输出题目，不要有任何额外解释"""

    success, result = chat_with_qwen([{"role": "user", "content": prompt}])
    
    if not success:
        return get_status_display(), f"生成题目失败: {result}", gr.update(choices=[], visible=False), gr.update(visible=False), gr.update(visible=False), ""
    
    # 解析题目 - 改进版本
    questions = []
    lines = result.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            # 尝试另一种解析方式 - 检查是否包含题型关键词
            if 'CHOICE|' in line or 'FILL|' in line or 'SHORT|' in line:
                # 提取包含题型的部分
                matches = re.findall(r'(CHOICE\|.*?|[^\n]+|[^\n]+|[^\n]+|[^\n]+|[^\n]+)|(FILL\|.*?|[^\n]+|[^\n]+)|(SHORT\|.*?|[^\n]+|[^\n]+)', line)
                if matches:
                    # 对于每个匹配项，重新解析
                    for match in matches:
                        if match[0]:  # CHOICE
                            parts = [p.strip() for p in match[0].split('|') if p.strip()]
                            if len(parts) >= 6 and parts[0].upper() == "CHOICE":
                                correct = parts[5].upper()
                                if correct in ['A', 'B', 'C']:
                                    questions.append({
                                        "type": "choice",
                                        "question": parts[1],
                                        "options": [parts[2], parts[3], parts[4]],
                                        "correct": correct
                                    })
                        elif match[1]:  # FILL
                            parts = [p.strip() for p in match[1].split('|') if p.strip()]
                            if len(parts) >= 3 and parts[0].upper() == "FILL":
                                questions.append({
                                    "type": "fill",
                                    "question": parts[1],
                                    "correct": parts[2]
                                })
                        elif match[2]:  # SHORT
                            parts = [p.strip() for p in match[2].split('|') if p.strip()]
                            if len(parts) >= 3 and parts[0].upper() == "SHORT":
                                questions.append({
                                    "type": "short",
                                    "question": parts[1],
                                    "correct": parts[2]
                                })
            continue
        
        parts = [p.strip() for p in line.split('|')]
        q_type = parts[0].upper()
        
        if q_type == "CHOICE" and len(parts) >= 6:
            correct = parts[5].upper()
            if correct in ['A', 'B', 'C']:
                questions.append({
                    "type": "choice",
                    "question": parts[1],
                    "options": [parts[2], parts[3], parts[4]],
                    "correct": correct
                })
        elif q_type == "FILL" and len(parts) >= 3:
            questions.append({
                "type": "fill",
                "question": parts[1],
                "correct": parts[2]
            })
        elif q_type == "SHORT" and len(parts) >= 3:
            questions.append({
                "type": "short",
                "question": parts[1],
                "correct": parts[2]
            })
    
    # 如果没有成功解析到题目，尝试更宽松的解析方式
    if not questions:
        # 尝试从AI的响应中提取题目
        # 查找选择题
        choice_matches = re.findall(r'CHOICE\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|([A-C])', result)
        for match in choice_matches:
            questions.append({
                "type": "choice",
                "question": match[0],
                "options": [match[1], match[2], match[3]],
                "correct": match[4]
            })
        
        # 查找填空题
        fill_matches = re.findall(r'FILL\|(.*?)\|(.*?)(?:\n|$)', result)
        for match in fill_matches:
            questions.append({
                "type": "fill",
                "question": match[0],
                "correct": match[1]
            })
        
        # 查找简答题
        short_matches = re.findall(r'SHORT\|(.*?)\|(.*?)(?:\n|$)', result)
        for match in short_matches:
            questions.append({
                "type": "short",
                "question": match[0],
                "correct": match[1]
            })
    
    if not questions:
        return get_status_display(), "生成问题失败，请重试", gr.update(choices=[], visible=False), gr.update(visible=False), gr.update(visible=False), ""
    
    user_state["current_questions"] = questions
    user_state["current_question_index"] = 0
    
    q = questions[0]
    return display_question(q, 1, len(questions))


def display_question(q, current_idx, total):
    """根据题型显示题目"""
    type_labels = {"choice": "选择题", "fill": "填空题", "short": "简答题"}
    type_emoji = {"choice": "A", "fill": "填", "short": "答"}
    
    question_display = f"""## [{type_emoji.get(q['type'], '?')}] 知识检测 ({current_idx}/{total}) - {type_labels.get(q['type'], '未知')}

### {q['question']}

---
"""
    
    if q["type"] == "choice":
        question_display += "*请选择正确答案~*"
        choices = [f"A. {q['options'][0]}", f"B. {q['options'][1]}", f"C. {q['options'][2]}"]
        return get_status_display(), question_display, gr.update(choices=choices, value=None, visible=True), gr.update(visible=True), gr.update(visible=False, value=""), ""
    elif q["type"] == "fill":
        question_display += "*请在下方输入答案（填空题）*"
        return get_status_display(), question_display, gr.update(choices=[], visible=False), gr.update(visible=True), gr.update(visible=True, value="", placeholder="请输入填空题答案..."), ""
    else:
        question_display += "*请在下方简要作答（简答题）*"
        return get_status_display(), question_display, gr.update(choices=[], visible=False), gr.update(visible=True), gr.update(visible=True, value="", placeholder="请输入你的答案..."), ""


def submit_answer(choice_answer, text_answer):
    """提交答案"""
    decay_energy()
    
    if not user_state["current_questions"]:
        return get_status_display(), "请先开始诊断！", gr.update(choices=[], visible=False), gr.update(visible=False), gr.update(visible=False), ""
    
    idx = user_state["current_question_index"]
    q = user_state["current_questions"][idx]
    total_questions = len(user_state["current_questions"])
    
    # 判断答案
    if q["type"] == "choice":
        if not choice_answer:
            return get_status_display(), "请先选择一个答案哦~", gr.update(visible=True), gr.update(visible=True), gr.update(visible=False), ""
        user_answer = choice_answer[0].upper()
        is_correct = (user_answer == q["correct"])
    else:
        if not text_answer or not text_answer.strip():
            return get_status_display(), "请先输入答案哦~", gr.update(visible=False), gr.update(visible=True), gr.update(visible=True), ""
        user_answer = text_answer.strip()
        
        # 根据题型采用不同的匹配策略
        if q["type"] == "fill":
            # 填空题：精确匹配（去除空白字符后完全相同）
            correct_lower = q["correct"].lower().replace(" ", "").replace("\n", "").replace("\t", "")
            answer_lower = user_answer.lower().replace(" ", "").replace("\n", "").replace("\t", "")
            is_correct = correct_lower == answer_lower
        else:  # 简答题
            # 简答题：模糊匹配（包含关系）
            correct_lower = q["correct"].lower().replace(" ", "")
            answer_lower = user_answer.lower().replace(" ", "")
            is_correct = (correct_lower in answer_lower) or (answer_lower in correct_lower)
    
    # 生成反馈
    if is_correct:
        user_state["knowledge_mastery"] = min(100, user_state["knowledge_mastery"] + 15)
        feedback_html = '<div style="background: #d4edda; border-radius: 12px; padding: 20px; text-align: center;"><div style="font-size: 48px;">正确!</div><div style="color: #155724;">复习进度 +15</div></div>'
        feedback_text = f"## 太棒了！\n\n你的答案：**{user_answer}**\n\n答对了！继续保持~\n\n---\n"
    else:
        feedback_html = '<div style="background: #fff3cd; border-radius: 12px; padding: 20px; text-align: center;"><div style="font-size: 48px;">再想想</div></div>'
        if q["type"] == "choice":
            correct_text = q["options"][ord(q["correct"]) - ord('A')]
            feedback_text = f"## 没关系~\n\n你选择了 **{user_answer}**，正确答案是 **{q['correct']}**\n\n**{q['correct']}. {correct_text}**\n\n---\n"
        else:
            feedback_text = f"## 参考一下~\n\n你的答案：{user_answer}\n\n**参考答案**：{q['correct']}\n\n---\n"
    
    # 下一题或完成
    user_state["current_question_index"] += 1
    
    if user_state["current_question_index"] < total_questions:
        next_q = user_state["current_questions"][user_state["current_question_index"]]
        next_idx = user_state["current_question_index"] + 1
        
        type_labels = {"choice": "选择题", "fill": "填空题", "short": "简答题"}
        next_display = f"""{feedback_text}
## 下一题 ({next_idx}/{total_questions}) - {type_labels.get(next_q['type'], '')}

### {next_q['question']}

---
"""
        if next_q["type"] == "choice":
            choices = [f"A. {next_q['options'][0]}", f"B. {next_q['options'][1]}", f"C. {next_q['options'][2]}"]
            return get_status_display(), next_display, gr.update(choices=choices, value=None, visible=True), gr.update(visible=True), gr.update(visible=False, value=""), feedback_html
        else:
            hint = "请输入填空题答案" if next_q["type"] == "fill" else "请输入你的答案"
            return get_status_display(), next_display, gr.update(choices=[], visible=False), gr.update(visible=True), gr.update(visible=True, value="", placeholder=hint), feedback_html
    else:
        final_mastery = user_state["knowledge_mastery"]
        complete_msg = f"""{feedback_text}
## 诊断完成！

你完成了全部 **{total_questions}** 道题目

**当前复习进度**: {final_mastery}%
"""
        user_state["current_questions"] = []
        user_state["current_question_index"] = 0
        
        return get_status_display(), complete_msg, gr.update(choices=[], visible=False), gr.update(visible=False), gr.update(visible=False), feedback_html


# ==================== 续命功能 ====================

def get_recommendations(preference):
    """获取校园补给推荐"""
    energy = user_state["energy_level"]
    pref_tags = [p.strip().lower() for p in preference.split(',') if p.strip()] if preference else []
    
    scored_anchors = []
    for anchor in CAMPUS_ANCHORS:
        score = anchor["recoveryValue"]
        matched = [tag for tag in anchor["tags"] if tag in pref_tags]
        score += len(matched) * 15
        if energy < 20:
            score += anchor["recoveryValue"] * 0.5
        scored_anchors.append({**anchor, "score": score, "matched": matched})
    
    scored_anchors.sort(key=lambda x: x["score"], reverse=True)
    top_anchors = scored_anchors[:3]
    
    result = "## 校园补给推荐\n\n"
    if energy < 20:
        result += "### 警告 情绪电量告急！强烈建议立即补给！\n\n"
    
    for i, anchor in enumerate(top_anchors, 1):
        emoji = ["1.", "2.", "3."][i-1]
        result += f"""### {emoji} {anchor['name']}

**位置**: {anchor['location']}
**恢复值**: +{anchor['recoveryValue']} 情绪电量
**标签**: {' '.join(['#' + tag for tag in anchor['tags']])}

{anchor['description']}

---
"""
    
    return get_status_display(), result


def do_recovery(anchor_name):
    """执行补给"""
    for anchor in CAMPUS_ANCHORS:
        if anchor["name"] == anchor_name:
            user_state["energy_level"] = min(100, user_state["energy_level"] + anchor["recoveryValue"])
            return get_status_display(), f"## 补给成功！\n\n在 **{anchor_name}** 休息了一会儿\n\n情绪电量 **+{anchor['recoveryValue']}**\n\n当前情绪电量：{user_state['energy_level']}%"
    return get_status_display(), "未找到该地点"


def save_energy_card(img, txt, current_album):
    """封存能量卡片"""
    if not img:
        return current_album, current_album, None, "", get_status_display()
    new_album = [(img, txt if txt else "美好瞬间")] + current_album
    user_state["energy_level"] = min(100, user_state["energy_level"] + 15)
    return new_album, new_album, None, "", get_status_display()


def checkin():
    """签到"""
    user_state["energy_level"] = min(100, user_state["energy_level"] + 15)
    return get_status_display()


def reset_state():
    """重置状态"""
    global document_store
    user_state["energy_level"] = 100
    user_state["knowledge_mastery"] = 0
    user_state["weak_points"] = []
    user_state["current_questions"] = []
    user_state["current_question_index"] = 0
    user_state["energy_album"] = []
    document_store = {"content": "", "source_file": "", "char_count": 0, "upload_time": None}
    return get_status_display()


def adjust_energy(value):
    user_state["energy_level"] = int(value)
    return get_status_display()


def adjust_mastery(value):
    user_state["knowledge_mastery"] = int(value)
    return get_status_display()


# ==================== Gradio 界面 ====================

custom_theme = gr.themes.Base(
    primary_hue=gr.themes.colors.pink,
    secondary_hue=gr.themes.colors.purple,
    neutral_hue=gr.themes.colors.slate,
).set(
    body_background_fill="#0f0f1a",
    block_background_fill="rgba(255, 255, 255, 0.03)",
    block_border_color="rgba(255, 255, 255, 0.1)",
    block_radius="20px",
    button_primary_background_fill="linear-gradient(135deg, #ff6b9d 0%, #c44eff 50%, #6e8efb 100%)",
    button_primary_text_color="white",
    input_background_fill="rgba(255, 255, 255, 0.05)",
    body_text_color="#e2e8f0",
)

custom_css = """
.gradio-container { max-width: 1200px !important; margin: 0 auto !important; }
button.primary { background: linear-gradient(135deg, #ff6b9d 0%, #c44eff 50%, #6e8efb 100%) !important; border: none !important; }
"""

with gr.Blocks(theme=custom_theme, css=custom_css, title="期末复习助手 (轻量版)") as demo:
    
    album_state = gr.State([])
    status_display = gr.HTML(get_status_display())
    
    with gr.Row():
        checkin_btn = gr.Button("每日签到", variant="primary", size="sm")
        reset_btn = gr.Button("重置状态", size="sm")
    
    with gr.Accordion("手动调整", open=False):
        energy_slider = gr.Slider(0, 100, value=100, step=5, label="情绪电量")
        mastery_slider = gr.Slider(0, 100, value=0, step=5, label="复习进度")
    
    with gr.Tabs():
        with gr.Tab("减负 - 考点梳理"):
            with gr.Column():
                file_input = gr.File(label="上传复习资料 (PDF/TXT)", file_types=[".txt", ".pdf", ".md"])
                text_input = gr.Textbox(label="或者直接输入知识点", lines=3)
                analyze_btn = gr.Button("萃取核心考点", variant="primary")
                analyze_status = gr.Textbox(label="状态", interactive=False)
                heatmap_output = gr.Markdown(label="考点地图", latex_delimiters=[{"left": "$$", "right": "$$", "display": True}, {"left": "$", "right": "$", "display": False}])
                gr.Markdown("---")
                gr.Markdown("### 智能问答")
                with gr.Row():
                    question_input = gr.Textbox(label="针对考点追问", scale=4)
                    query_btn = gr.Button("解答", scale=1)
                answer_output = gr.Markdown(latex_delimiters=[{"left": "$$", "right": "$$", "display": True}, {"left": "$", "right": "$", "display": False}])

        with gr.Tab("诊断 - 知识对练"):
            with gr.Column():
                start_btn = gr.Button("开始费曼自测", variant="primary")
                question_display = gr.Markdown("准备好了吗？点击开始，我会根据考点考考你。", latex_delimiters=[{"left": "$$", "right": "$$", "display": True}, {"left": "$", "right": "$", "display": False}])
                answer_input = gr.Radio(label="请选择你的答案", choices=[], visible=False)
                text_answer_input = gr.Textbox(label="请输入你的答案", placeholder="填空题/简答题请在此输入...", visible=False)
                feedback_display = gr.HTML(value="")
                submit_btn = gr.Button("提交回答", variant="primary", visible=False)

        with gr.Tab("续命 - 能量补给"):
            gr.Markdown("### 能量相册打卡\n上传校园瞬间，提升 15% 精神值。")
            with gr.Row():
                with gr.Column(scale=1):
                    photo_input = gr.Image(label="捕捉瞬间", type="filepath")
                    mood_tag_input = gr.Textbox(label="心情标签", placeholder="写下这一刻的碎碎念...")
                    save_card_btn = gr.Button("封存这张能量卡", variant="primary")
                with gr.Column(scale=2):
                    energy_gallery = gr.Gallery(label="我的能量相册", columns=2, height=400)
            
            gr.Markdown("---")
            gr.Markdown("### 校园精准补给\n输入你的偏好（如：cat, coffee），寻找回血圣地。")
            with gr.Row():
                pref_input = gr.Textbox(placeholder="偏好标签...", label="偏好")
                recommend_btn = gr.Button("获取推荐")
            recommend_output = gr.Markdown()
            
            gr.Markdown("---")
            gr.Markdown("### 快速补给")
            with gr.Row():
                anchor_dropdown = gr.Dropdown(choices=[a["name"] for a in CAMPUS_ANCHORS], label="选择补给点")
                recover_btn = gr.Button("立即前往")
            recover_output = gr.Markdown()

    # 事件绑定
    checkin_btn.click(checkin, outputs=[status_display])
    reset_btn.click(reset_state, outputs=[status_display])
    energy_slider.change(adjust_energy, inputs=[energy_slider], outputs=[status_display])
    mastery_slider.change(adjust_mastery, inputs=[mastery_slider], outputs=[status_display])
    
    analyze_btn.click(analyze_document, inputs=[file_input, text_input], outputs=[status_display, heatmap_output, analyze_status])
    query_btn.click(rag_query, inputs=[question_input], outputs=[status_display, answer_output])
    
    start_btn.click(start_diagnosis, outputs=[status_display, question_display, answer_input, submit_btn, text_answer_input, feedback_display])
    submit_btn.click(submit_answer, inputs=[answer_input, text_answer_input], outputs=[status_display, question_display, answer_input, submit_btn, text_answer_input, feedback_display])
    
    save_card_btn.click(save_energy_card, inputs=[photo_input, mood_tag_input, album_state], outputs=[energy_gallery, album_state, photo_input, mood_tag_input, status_display])
    recommend_btn.click(get_recommendations, inputs=[pref_input], outputs=[status_display, recommend_output])
    recover_btn.click(do_recovery, inputs=[anchor_dropdown], outputs=[status_display, recover_output])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860
    )
