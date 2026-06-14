# Nginx API 反向代理示例

本文给出公告查询 API 的 nginx 配置示例。API 服务与对应区域的爬虫服务部署在同一区域，并连接同一区域的爬虫数据库；爬虫项目本身不对外提供 API。

nginx 只负责按域名转发到对应区域的 API 实例。数据隔离必须由 API 自身的 `DATA_REGION`、数据库连接和国家校验规则共同保证。

## 1. 路由原则

- 欧盟域名只转发到欧盟 API 实例。
- 新加坡域名只转发到新加坡 API 实例。
- nginx 不根据 `country` 参数判断区域，避免把业务规则放到网关层。
- API 查询必须继续在 SQL 中带上 `data_region = :DATA_REGION`。
- 跨区国家查询由 API 返回 `403`。

示例域名：

```text
api-eu.example.com -> prod-eu API
api-sg.example.com -> prod-sg API
api-test.example.com -> test API
api-test-sg.example.com -> test-sg API
```

示例端口：

```text
prod-eu API    -> 127.0.0.1:8100
prod-sg API    -> 127.0.0.1:8101
test API       -> 127.0.0.1:8110
test-sg API    -> 127.0.0.1:8111
```

实际端口以 API 服务的 `.env`、compose 或 systemd 配置为准。

## 2. 产线示例

```nginx
upstream scopeslab_api_prod_eu {
    server 127.0.0.1:8100;
    keepalive 32;
}

upstream scopeslab_api_prod_sg {
    server 127.0.0.1:8101;
    keepalive 32;
}

server {
    listen 80;
    server_name api-eu.example.com;

    location /api/v1/config/health {
        proxy_pass http://scopeslab_api_prod_eu/api/v1/config/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/v1/ {
        proxy_pass http://scopeslab_api_prod_eu;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}

server {
    listen 80;
    server_name api-sg.example.com;

    location /api/v1/config/health {
        proxy_pass http://scopeslab_api_prod_sg/api/v1/config/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/v1/ {
        proxy_pass http://scopeslab_api_prod_sg;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

如果服务器已配置 HTTPS，建议保留 HTTP 到 HTTPS 跳转，并把上面的反代配置放到 `listen 443 ssl http2;` 的 server 中。

## 3. 测试环境示例

测试环境如果 `test` 和 `test-sg` 共用同一台服务器，建议使用两个域名或两个子域名，分别指向不同 API 端口。

```nginx
upstream scopeslab_api_test {
    server 127.0.0.1:8110;
    keepalive 16;
}

upstream scopeslab_api_test_sg {
    server 127.0.0.1:8111;
    keepalive 16;
}

server {
    listen 80;
    server_name api-test.example.com;

    location /api/v1/ {
        proxy_pass http://scopeslab_api_test;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name api-test-sg.example.com;

    location /api/v1/ {
        proxy_pass http://scopeslab_api_test_sg;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. 校验命令

修改 nginx 配置后先检查语法：

```bash
sudo nginx -t
```

语法通过后再 reload：

```bash
sudo systemctl reload nginx
```

从 nginx 所在服务器本机验证 upstream：

```bash
curl -i http://127.0.0.1:8100/api/v1/config/health
curl -i http://127.0.0.1:8101/api/v1/config/health
```

从外部验证域名路由：

```bash
curl -i https://api-eu.example.com/api/v1/config/health
curl -i https://api-sg.example.com/api/v1/config/health
curl -i "https://api-eu.example.com/api/v1/notices?country=DEU&page=1&per_page=20"
curl -i "https://api-sg.example.com/api/v1/notices?country=SGP&page=1&per_page=20"
```

预期：

- 欧盟域名可以查询 `FRA`、`BEL`、`DEU`、`NLD`、`ITA`、`ESP`。
- 新加坡域名可以查询 `SGP`。
- 跨区国家应由 API 返回 `403`，而不是由 nginx 处理。

## 5. 常见问题

### 5.1 域名打到了错误区域

检查 `server_name` 和 `proxy_pass` 指向的 upstream：

```bash
sudo nginx -T | grep -E 'server_name|proxy_pass|upstream scopeslab_api' -n
```

再检查对应 API 实例的 `.env`：

```bash
grep -E 'DATA_REGION|DATABASE_URL|API_KEYS_JSON' .env
```

### 5.2 nginx 正常但查询不到数据

优先确认 API 连接的是当前区域数据库，并且查询条件中包含 `data_region`：

```sql
SELECT data_region, country_code, count(*)
FROM crawler_notices
GROUP BY data_region, country_code
ORDER BY data_region, country_code;
```

如果数据库有数据但接口为空，检查 `country` 参数是否为三位码，以及 API 是否正确转换到了库里的二位 `country_code`。

### 5.3 Docker 内 API 访问宿主机数据库失败

如果 API 也运行在 Docker 中，且 PostgreSQL、Redis、MinIO 在宿主机，仍然需要按 compose project 的 Docker bridge 网段放行防火墙和 `pg_hba.conf`。处理方式参考爬虫项目的 `docs/guides/DEPLOYMENT_TROUBLESHOOTING_CN.md`。
