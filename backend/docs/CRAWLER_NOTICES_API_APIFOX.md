# Apifox 调试配置：公告查询接口

本文给出 `/api/v1/notices` 的 Apifox 请求配置。接口使用 AK/SK 签名认证。

## 1. 环境变量

在 Apifox Environment 中新增：

| 变量名 | 示例值 | 说明 |
| --- | --- | --- |
| `base_url` | `https://api-test.example.com` | API 域名，不带结尾 `/` |
| `api_key` | `partner-test-eu` | 对应 `.env` 里的 `API_KEYS_JSON` key |
| `api_secret` | `replace-with-secret` | 对应 key 的 secret |
| `country` | `DEU` | EU 可用 `FRA/BEL/DEU/NLD/ITA/ESP`，SG 用 `SGP` |
| `page` | `1` | 页码 |
| `per_page` | `20` | 每页数量，最大 `100` |

## 2. 请求信息

```text
Method: GET
URL: {{base_url}}/api/v1/notices
```

Query 参数：

| 参数 | 值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `country` | `{{country}}` | 是 | 三位国家码 |
| `page` | `{{page}}` | 否 | 默认 `1` |
| `per_page` | `{{per_page}}` | 否 | 默认 `20`，最大 `100` |

Headers：

| Header | 值 |
| --- | --- |
| `X-Api-Key` | `{{api_key}}` |
| `X-Timestamp` | `{{timestamp}}` |
| `X-Nonce` | `{{nonce}}` |
| `X-Signature` | `{{signature}}` |

Body：无。

## 3. Apifox 预请求脚本

在请求的「前置操作 / Pre-request Script」中加入：

```javascript
const apiKey = pm.environment.get("api_key");
const apiSecret = pm.environment.get("api_secret");

const timestamp = Math.floor(Date.now() / 1000).toString();
const nonce = `${timestamp}-${Math.random().toString(16).slice(2)}`;

const method = pm.request.method.toUpperCase();
const path = "/api/v1/notices";

const queryItems = [];
for (const item of pm.request.url.query.all()) {
  if (!item.disabled) {
    queryItems.push([
      pm.variables.replaceIn(item.key),
      pm.variables.replaceIn(item.value),
    ]);
  }
}
queryItems.sort((a, b) => {
  if (a[0] === b[0]) {
    return String(a[1]).localeCompare(String(b[1]));
  }
  return String(a[0]).localeCompare(String(b[0]));
});
const canonicalQuery = queryItems
  .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
  .join("&");

const bodyHash = CryptoJS.SHA256("").toString(CryptoJS.enc.Hex);
const payload = [
  method,
  path,
  canonicalQuery,
  timestamp,
  nonce,
  bodyHash,
].join("\n");

const signature = CryptoJS.HmacSHA256(payload, apiSecret).toString(CryptoJS.enc.Hex);

pm.environment.set("timestamp", timestamp);
pm.environment.set("nonce", nonce);
pm.environment.set("signature", signature);

pm.request.headers.upsert({ key: "X-Api-Key", value: apiKey });
pm.request.headers.upsert({ key: "X-Timestamp", value: timestamp });
pm.request.headers.upsert({ key: "X-Nonce", value: nonce });
pm.request.headers.upsert({ key: "X-Signature", value: signature });
```

签名内容必须与服务端一致：

```text
METHOD\nPATH\nCANONICAL_QUERY\nTIMESTAMP\nNONCE\nSHA256_BODY
```

GET 请求 body 为空，所以 `SHA256_BODY` 是空字符串的 SHA256：

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## 4. EU 测试请求

环境变量：

```text
base_url=https://api-test.example.com
api_key=partner-test-eu
api_secret=replace-with-secret
country=DEU
page=1
per_page=20
```

预期：

- `DATA_REGION=EU` 时成功
- 返回 `code=200`
- `data.items[].country_code` 为三位码，例如 `DEU`

## 5. SG 测试请求

环境变量：

```text
base_url=https://api-test-sg.example.com
api_key=partner-test-sg
api_secret=replace-with-secret
country=SGP
page=1
per_page=20
```

预期：

- `DATA_REGION=SG` 时成功
- 返回 `code=200`
- `data.items[].country_code=SGP`

## 6. 跨区校验请求

EU 域名查询新加坡：

```text
base_url=https://api-test.example.com
country=SGP
```

预期：

```json
{
  "code": 403,
  "message": "Country is not allowed in this data region"
}
```

SG 域名查询德国：

```text
base_url=https://api-test-sg.example.com
country=DEU
```

预期同样返回 `403`。

## 7. 常见错误

### 7.1 `401 Invalid signature`

检查：

- `api_secret` 是否和服务器 `.env` 一致
- Query 参数是否参与签名
- `path` 是否固定为 `/api/v1/notices`
- Apifox 是否重复自动编码了 query

### 7.2 `401 Expired X-Timestamp`

服务器默认允许窗口是 `API_SIGNATURE_TTL_SECONDS=300`。检查本机时间和服务器时间是否相差超过 5 分钟。

### 7.3 `401 Replayed X-Nonce`

同一个 nonce 不能重复使用。重新发送请求前让预请求脚本生成新的 nonce。

### 7.4 `422 Validation error`

常见原因：

- `country` 不是三位码
- `per_page` 大于 `100`
- `page` 小于 `1`
