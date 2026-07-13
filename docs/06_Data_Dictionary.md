# 数据字典

## CSV业务数据

### products.csv

商品知识卡。核心字段：商品编码、名称、类别、面料、版型、适用顾客、标签、别名、卖点、搭配、尺码、异议、话术、禁止承诺、版本和有效期。

### barcodes.csv

条码映射。字段：`barcode`、`product_code`、`status`。

### inventory.csv

分门店和尺码库存。字段：商品编码、门店、尺码、库存数量、标价、活动参考价、调货天数、更新时间。

### knowledge_docs.csv

门店规则、售后制度、活动制度和服务SOP。包含版本、有效期、适用范围、风险等级、来源章节和正文。

### product_recommendations.csv

固定连带推荐关系。动态推荐由标签和库存补充。

## SQLite业务表

| 表 | 用途 |
|---|---|
| stores | 门店、区域和营业状态 |
| users | 用户、角色、门店和区域 |
| questions | 问答、意图、风险、回答和来源 |
| reviews | 一级/二级审批、优先级、时限、升级原因和结果 |
| notifications | 审批、升级、新品和知识申请通知 |
| feedback | Bad Case类型、状态、责任人、优化和验证 |
| knowledge_requests | 店长提交的知识库优化申请 |
| product_requests | 未识别商品建档、补充、审核和发布流程 |
| rule_acknowledgements | 规则版本已读确认 |
| audit_logs | 操作人、时间、实体、修改前后内容 |
| user_sessions | 活跃度和使用时长 |
| complaint_logs | 可选客诉关联数据 |
| error_logs | 后台错误记录 |

## 关键状态

### reviews.review_status

- `pending_manager`
- `pending_regional`
- `confirmed`
- `corrected`
- `rejected`

### feedback.processing_status

- 待处理
- 处理中
- 已优化
- 已关闭

### product_requests.status

- 待店长补充
- 待区域审核
- 运营退回修改
- 已发布
- 已驳回

## usage_events 功能使用事件

| 字段 | 说明 |
|---|---|
| event_id | 事件ID |
| user_id | 操作用户 |
| store_id | 所属门店 |
| event_type | 导购查询、快捷算价、连带推荐加入算价、淡场学习等 |
| entity_type/entity_id | 关联商品、问题、测验或算价 |
| metadata_json | 商品列表、金额、活动、推荐逻辑等上下文 |
| created_at | 发生时间 |

## learning_results 淡场学习结果

| 字段 | 说明 |
|---|---|
| user_id/store_id | 导购与门店 |
| question_key | 固定题目键 |
| category | 商品、售后、活动、SOP等 |
| selected_answer | 导购选择 |
| is_correct | 是否正确 |
| practice_date | 练习日期 |
| created_at | 提交时间 |

## feedback 扩展字段

| 字段 | 说明 |
|---|---|
| due_at | 处理时限 |
| evidence_path | 现场凭证图片路径 |
| cluster_key | 同类问题聚合标签 |
| updated_at | 最近更新时间 |
