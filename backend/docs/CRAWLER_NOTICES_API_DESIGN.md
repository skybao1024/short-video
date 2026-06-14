# 爬虫公告查询 API 方案

## 1. 目标

使用当前 FastAPI 项目作为爬虫公告数据的 API 层。API 跟随每个区域的爬虫服务一起部署，并读取同一个区域的 PostgreSQL 数据库。

第一阶段只提供只读查询接口，数据来源是 `crawler_notices`，用于按国家查询采购公告，返回标题、描述和采购网址等字段。

## 2. 部署模型

API 按区域分别部署：

- EU 部署：部署在欧洲服务器，连接欧洲爬虫数据库，配置 `DATA_REGION=EU`。
- SG 部署：部署在新加坡服务器，连接新加坡爬虫数据库，配置 `DATA_REGION=SG`。

外部请求由 nginx 按域名分发到不同区域服务器。即使 nginx 已经做了域名分流，API 内部仍然必须校验区域，不能只依赖 nginx。

## 3. 认证方案建议

当前模板项目已有 JWT 登录认证：

- client 用户认证：`app/api/client/deps.py:get_current_user`
- backoffice 管理员认证：`app/api/backoffice/deps.py:get_current_admin`
- token 生成和校验：`app/core/security.py`

这套认证更适合用户登录和后台管理，不太适合第三方系统调用。第三方调用属于服务端到服务端的 B2B API，建议新增独立的 AK/SK 认证，不复用用户登录。

推荐请求头：

```text
X-Api-Key: <access key>
X-Timestamp: <unix 秒级时间戳或 ISO 时间>
X-Nonce: <随机唯一字符串>
X-Signature: <HMAC-SHA256 十六进制签名>
```

推荐签名内容：

```text
METHOD\nPATH\nCANONICAL_QUERY\nTIMESTAMP\nNONCE\nSHA256_BODY
```

服务端校验逻辑：

- 根据 `X-Api-Key` 找到对应 secret。
- 使用 secret 重新计算 HMAC-SHA256 签名。
- 校验 timestamp 是否在允许窗口内，例如 5 分钟。
- 如果 Redis 可用，记录 nonce，防止同一签名被重放。
- 后续可以按 key 做限流、禁用、轮换和审计。

如果只是先做内部联调，可以短期使用静态 `X-Api-Key`，但正式对第三方开放时建议使用 AK/SK。

## 4. 配置建议

API 数据库连接参考爬虫项目的做法：部署时通过 `.env` 提供一个明确的数据库 URL。FastAPI 使用 async SQLAlchemy，所以这里直接使用 `asyncpg` 驱动，不做 `psycopg`、普通 `postgresql://` 等连接串的自动兼容转换。

```text
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<postgres_host>:5432/<database>
```

为了支持爬虫 API，建议新增：

```text
DATA_REGION=EU|SG
API_AUTH_MODE=aksk
API_KEYS_JSON={...}
API_SIGNATURE_TTL_SECONDS=300
```

第一版不建议额外增加 YAML 配置文件。当前 FastAPI 模板已经统一使用 `.env` + `pydantic-settings`，部署时也会通过服务器本地 `.env` 注入数据库、Redis、密钥等敏感配置。继续使用 `.env` 有几个好处：

- 和模板现有配置体系一致，不增加第二套配置加载逻辑。
- 和爬虫服务当前部署方式一致，区域差异由每台服务器自己的 `.env` 控制。
- AK/SK、数据库密码、Redis 密码都属于敏感信息，不适合提交到仓库中的 YAML。
- 本地开发继续使用 `.env`，保持和测试、产线相同的配置入口；如果后续需要 `.env.local`，再单独增加加载逻辑。

`API_KEYS_JSON` 第一版可以放在 `.env` 中，例如：

```env
API_KEYS_JSON={"partner-eu-1":{"secret":"replace-with-secret","enabled":true},"partner-sg-1":{"secret":"replace-with-secret","enabled":true}}
```

如果后续第三方很多、需要后台管理 key、轮换 key、审计调用量，再升级为数据库表或外部 secret manager。

API 建议使用只读数据库账号，只需要对 `crawler_notices` 有 `SELECT` 权限。后续如果接口要返回采购入口状态，再额外给 `crawler_buyer_portal_links` 的只读权限。

## 5. 公告查询接口

建议接口：

```text
GET /api/v1/notices
```

查询参数：

```text
country=FRA|BEL|DEU|NLD|ITA|ESP|SGP
page=1
per_page=20
```

第一版国家参数只支持 ISO 3166-1 alpha-3 三位码。调用方必须按该规则传参，不再同时兼容二位码。

分页限制：

```text
per_page 最大值为 100
```

第一版返回字段：

```json
{
  "items": [
    {
      "id": "123456789",
      "title": "公告标题",
      "description": "公告描述",
      "procurement_url": "https://buyer.example/tender/1",
      "notice_url": "https://official.example/notice/1",
      "country_code": "DEU",
      "publication_date": "2026-06-10",
      "deadline": "2026-07-01T12:00:00+02:00",
      "updated_at": "2026-06-11T10:30:00+00:00"
    }
  ],
  "page": 1,
  "per_page": 20,
  "total": 123
}
```

`procurement_url` 建议优先使用采购方门户地址，如果没有再退回官方公告地址：

```sql
COALESCE(buyer_portal_url, notice_url)
```

## 6. 区域和国家校验规则

接口必须同时校验部署区域和请求国家。

API 对外只接收三位国家码，内部查询时转换为 `crawler_notices.country_code` 使用的二位码：

```text
FRA -> FR -> EU
BEL -> BE -> EU
DEU -> DE -> EU
NLD -> NL -> EU
ITA -> IT -> EU
ESP -> ES -> EU
SGP -> SG -> SG
```

要求：

- `DATA_REGION=EU` 时，只允许查询 EU 国家。
- `DATA_REGION=SG` 时，只允许查询 SG。
- 跨区查询必须拒绝，返回 `403`。
- 每条 SQL 查询都必须包含 `crawler_notices.data_region = settings.DATA_REGION`。
- 国家查询必须使用转换后的二位国家码，例如 `DEU` 转为 `DE`。

SQL 形态建议：

```sql
SELECT id,
       title,
       description,
       COALESCE(buyer_portal_url, notice_url) AS procurement_url,
       notice_url,
       country_code,
       publication_date,
       deadline,
       updated_at
FROM crawler_notices
WHERE data_region = :data_region
  AND country_code = :country_code
ORDER BY updated_at DESC NULLS LAST, id DESC
LIMIT :limit OFFSET :offset;
```

## 7. 最小实现范围

建议新增或修改这些文件：

```text
app/core/config.py                  # 增加 DATABASE_URL、DATA_REGION、API 认证配置
app/db/base.py                      # 使用 DATABASE_URL 创建 async SQLAlchemy engine
app/api/public/deps.py              # 新增 AK/SK 认证依赖，或放在 client deps 中
app/api/client/v1/notices.py        # 新增公告查询接口
app/schemas/client/notices.py       # 新增请求和响应 schema
app/route/router_registry.py        # 注册 notices 路由
```

建议边界：

- 保留现有 client JWT 和 backoffice JWT，不做破坏性改造。
- 第三方接口使用独立 AK/SK 依赖。
- `crawler_notices` 只读，不建议让 API 项目的 Alembic 迁移接管该表。
- API 项目自己的 `users`、`admins`、`tokens` 等表可以继续由模板项目管理，但要明确它们不是爬虫表。

## 8. 待确认问题

当前确认结果：

- AK/SK 第一版放在 `.env` 的 `API_KEYS_JSON` 中，不新建数据库表。
- 接口路径使用 `/api/v1/notices`。
- 国家参数只支持三位码：`FRA`、`BEL`、`DEU`、`NLD`、`ITA`、`ESP`、`SGP`。
- 跨区查询返回 `403`。
- `per_page` 最大值为 `100`。
- `procurement_url` 优先使用 `buyer_portal_url`，没有再使用 `notice_url`。
- 第一版暂时不支持关键词搜索 `q`。
- 排序按 `updated_at` 倒序。
- 返回的 `id` 使用内部 Snowflake ID。
- 第一版不新增 YAML 配置文件，本地、测试、产线都沿用 `.env`。

排序 SQL 调整为：

```sql
ORDER BY updated_at DESC NULLS LAST, id DESC
```
