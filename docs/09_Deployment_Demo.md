# 作品演示部署说明

## 1. 演示架构

```text
GitHub仓库
   ↓
Streamlit Community Cloud
   ↓
临时演示数据目录（CSV + SQLite）
   ↓
定时/手动恢复初始数据
```

该模式用于作品展示，不用于真实门店经营。所有商品、库存、价格、人员和经营数据均为模拟数据。

## 2. 为什么采用临时SQLite

公开作品演示的重点是让访问者体验完整流程，而不是长期保存访问者产生的数据。应用启动时会把仓库内的静态资料复制到临时运行目录，并在临时目录中创建SQLite业务库。这样可以：

- 避免公开访客改写Git仓库中的商品和规则文件；
- 允许体验问答、审批、反馈、通知和看板；
- 定时恢复初始演示状态；
- 不依赖额外数据库账号即可一键部署。

正式企业部署仍应使用托管数据库和对象存储。

## 3. 部署前检查

- [ ] 删除 `.venv`、`.pytest_cache`、本地日志和数据库文件
- [ ] 确认 `.streamlit/secrets.toml` 未进入Git
- [ ] 确认 `.gitignore` 包含 `.env`、`*.db`、`data/uploads/`
- [ ] 执行 `python -m pytest -q`
- [ ] 执行 `python scripts/run_eval.py`
- [ ] 本地启动 `python -m streamlit run streamlit_app.py`
- [ ] 检查页面顶部模拟数据提示
- [ ] 检查区域运营侧边栏的“重置演示数据”

## 4. Community Cloud配置

入口文件：

```text
streamlit_app.py
```

推荐Python：

```text
3.11
```

推荐Secrets：

```toml
APP_MODE = "demo"
AUTH_MODE = "demo"
DEMO_RESET_MINUTES = 60
DEMO_SHOW_ROLE_SWITCHER = true
DEMO_ALLOW_CATALOG_WRITES = false
SIMULATED_INVENTORY = true
DEMO_ACCESS_CODE = ""
API_DEMO_TOKEN = ""
LLM_API_KEY = ""
LLM_BASE_URL = "https://api.openai.com/v1"
LLM_MODEL = "gpt-4.1-mini"
RFC_BUSINESS_DATE = "2026-07-15"
RFC_TOP_K = 5
RFC_MIN_SCORE = 0.055
```

## 5. 访问策略

### 公开链接

适合作品集。建议：

- 设置访问口令；
- 关闭商品、规则和推荐配置写入；
- 保留导购、店长和区域运营演示角色；
- 每30—60分钟自动重置数据。

### 私有链接

适合定向发给面试官。可以在Community Cloud中限制查看者，也可以启用OIDC模式。

## 6. 可选OIDC模式

将：

```toml
AUTH_MODE = "oidc"
```

并按Streamlit认证配置提供 `[auth]` 段。登录邮箱必须预先写入 `users.email`，系统再根据数据库映射角色和门店。OIDC只完成“用户是谁”的认证，角色和数据范围仍由应用数据库控制。

## 7. FastAPI演示保护

如果FastAPI仅本地使用，不需要额外配置。若单独公开部署，建议设置：

```toml
API_DEMO_TOKEN = "随机长字符串"
```

所有需要用户身份的接口同时发送：

```text
X-User-Id: 2
X-Demo-Token: 随机长字符串
```

## 8. 大模型密钥

不配置 `LLM_API_KEY` 时，项目仍可运行。配置后必须通过Community Cloud Secrets或本地未提交的 `secrets.toml` 提供。任何曾提交到Git历史的密钥都应立即撤销并重新生成。

## 9. 正式企业版差异

企业部署需要额外完成：

- 企业OIDC/SSO和离职账号回收；
- PostgreSQL/MySQL持久化和备份；
- 对象存储保存图片凭证；
- ERP/POS/WMS实时库存和价格接口；
- HTTPS、限流、监控、告警和日志脱敏；
- 法务、信息安全和业务规则审核。
