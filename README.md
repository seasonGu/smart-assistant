# 个人智能助手

一个可扩展的 AI 助手平台，目前集成了文档助手和股票助手。

## 项目结构

```
smart-assistant/
├── backend/
│   ├── main.py              # FastAPI 后端
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量模板
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.vue           # 根组件（侧边栏布局）
        ├── main.js
        ├── style.css
        ├── router/index.js
        ├── store/index.js    # Pinia 状态管理
        ├── api/index.js      # 后端 API 封装
        └── views/
            ├── Home.vue      # 首页
            └── Chat.vue      # 对话页
```

## 快速启动

### 1. 后端

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 DASHSCOPE_API_KEY

# 启动服务
DASHSCOPE_API_KEY=your_key uvicorn main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

## 新增助手

在 `backend/main.py` 的 `ASSISTANTS` 字典中添加新条目：

```python
ASSISTANTS["my_assistant"] = {
    "id": "my_assistant",
    "name": "我的助手",
    "description": "助手描述",
    "icon": "🤖",
    "suggestions": ["示例问题1", "示例问题2"],
    "system_prompt": "你是...",
    "tools": [],  # 可选工具列表
}
```

## 技术栈

- 后端：Python · FastAPI · Qwen-Agent · DashScope
- 前端：Vue 3 · Pinia · Vue Router · Vite
- 数据库：MySQL（通过 SQLAlchemy 连接）
