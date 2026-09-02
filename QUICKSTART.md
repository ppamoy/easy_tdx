# easy_tdx 开发环境快速启动指南

## 环境要求
- Python 3.10+
- Node.js 18+
- npm 9+

## 一键启动

```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate
python scripts/dev_server.py
```

## 手动启动

### 后端 (FastAPI)
```bash
source .venv/bin/activate
easy-tdx serve --host 0.0.0.0 --port 8000
```

### 前端 (Vite)
```bash
cd web-ui
npm install  # 首次需要
npm run dev
```

## 访问地址
- 前端: http://localhost:3012
- 缠论分析: http://localhost:3012/chanlun
- API文档: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/api/v1/health

## 运行测试

```bash
# 缠论管道测试
python tests/scripts/test_chanlun_pipeline.py

# 模型验证
python scripts/verify_chanlun_model.py

# 单元测试
python -m pytest tests/unit/test_chanlun_v87_comprehensive.py -xvs
python -m pytest tests/unit/test_chanlun_v86_bi_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_zs_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_xd_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_signal_accuracy.py -xvs
```

## 浏览器控制台检查

打开 http://localhost:3012/chanlun，按 F12 打开开发者工具：

```javascript
// 1. 检查 JavaScript 错误
// Console 标签应无红色错误

// 2. 检查缠论图表
console.log(window.__CHANLUN_CHART__)

// 3. 测试 API
fetch('/api/v1/chanlun/analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({market: 'SZ', code: '000001', category: 'DAY', count: 500, start: 0})
}).then(r => r.json()).then(d => {
  console.log('笔数:', d.bi_count);
  console.log('中枢数:', d.zs_count);
  console.log('买卖点数:', d.mmd_count);
}).catch(e => console.error('API错误:', e));
```
