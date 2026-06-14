# 公告查询 API 部署手册

本文只记录部署操作。Runner 注册、网络排查、日志、回滚和常见问题见 [CRAWLER_NOTICES_API_RUNBOOK.md](CRAWLER_NOTICES_API_RUNBOOK.md)。

## 1. 部署目标

```text
test     -> /opt/scopeslab-api         -> scopeslab-api-test     -> API_PORT=8110
test-sg  -> /opt/scopeslab-api-test-sg -> scopeslab-api-test-sg  -> API_PORT=8111
prod-eu  -> /opt/scopeslab-api         -> scopeslab-api-prod-eu  -> API_PORT=8100
prod-sg  -> /opt/scopeslab-api         -> scopeslab-api-prod-sg  -> API_PORT=8101
```

测试环境 `test` 和 `test-sg` 可以部署在同一台服务器，但必须使用不同目录、不同 `.env`、不同 compose project、不同端口。

## 2. 首次部署准备

测试服务器：

```bash
sudo mkdir -p /opt/scopeslab-api/logs
sudo mkdir -p /opt/scopeslab-api-test-sg/logs
sudo chown -R "$USER":"$USER" /opt/scopeslab-api /opt/scopeslab-api-test-sg
```

产线服务器：

```bash
sudo mkdir -p /opt/scopeslab-api/logs
sudo chown -R "$USER":"$USER" /opt/scopeslab-api
```

目标目录必须提前放好 `.env`。发布流程不会覆盖 `.env`。

## 3. 首次部署网络放行

API 容器需要访问服务器上的 PostgreSQL 和 Redis。每个 compose project 会创建自己的 Docker bridge 网段，因此 `test` 和 `test-sg` 要分别确认和放行。

查看 Docker 网段：

```bash
docker network inspect scopeslab-api-test_app-network \
  --format '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}}{{end}}'

docker network inspect scopeslab-api-test-sg_app-network \
  --format '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}}{{end}}'
```

按实际网段放行 PostgreSQL 和 Redis，例如：

```bash
sudo ufw allow from 172.25.0.0/16 to any port 5432 proto tcp
sudo ufw allow from 172.25.0.0/16 to any port 6379 proto tcp
sudo ufw allow from 172.26.0.0/16 to any port 5432 proto tcp
sudo ufw allow from 172.26.0.0/16 to any port 6379 proto tcp
sudo ufw reload
```

如果 PostgreSQL 报 `no pg_hba.conf entry`，需要放行对应 Docker 网段。

查找 `pg_hba.conf`：

```bash
sudo -u postgres psql -c "SHOW hba_file;"
```

编辑输出路径，例如：

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

按实际库名、用户名和 Docker 网段增加规则，例如：

```conf
host    crawler       crawler       172.25.0.0/16    scram-sha-256
host    crawler-sg    crawler-sg    172.26.0.0/16    scram-sha-256
```

如果现有规则使用 `md5`，这里也保持 `md5`。保存后重载 PostgreSQL：

```bash
sudo systemctl reload postgresql
```

或：

```bash
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

验证：

```bash
docker compose -p scopeslab-api-test --env-file .env exec app \
  python -c "import socket; socket.create_connection(('192.168.88.151', 5432), 5); print('pg tcp ok')"

curl -sS http://127.0.0.1:8110/api/v1/config/health
curl -sS http://127.0.0.1:8111/api/v1/config/health
```

期望 `database` 和 `redis` 都是 `up`。

## 4. `.env` 最小配置

### 4.1 `test`

路径：`/opt/scopeslab-api/.env`

```env
ENV=testing
PROJECT_NAME=scopeslab-api-test
API_V1_STR=/api/v1
API_PORT=8110

DATABASE_URL=postgresql+asyncpg://crawler_api:replace-with-password@192.168.88.151:5432/crawler
DATA_REGION=EU

REDIS_HOST=192.168.88.151
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-redis-password

SECRET_KEY=replace-with-long-random-secret
API_AUTH_MODE=aksk
API_KEYS_JSON={"partner-test-eu":{"secret":"replace-with-secret","enabled":true}}
API_SIGNATURE_TTL_SECONDS=300
```

### 4.2 `test-sg`

路径：`/opt/scopeslab-api-test-sg/.env`

```env
ENV=testing
PROJECT_NAME=scopeslab-api-test-sg
API_V1_STR=/api/v1
API_PORT=8111

DATABASE_URL=postgresql+asyncpg://crawler_api_sg:replace-with-password@192.168.88.151:5432/crawler-sg
DATA_REGION=SG

REDIS_HOST=192.168.88.151
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-redis-password

SECRET_KEY=replace-with-long-random-secret
API_AUTH_MODE=aksk
API_KEYS_JSON={"partner-test-sg":{"secret":"replace-with-secret","enabled":true}}
API_SIGNATURE_TTL_SECONDS=300
```

### 4.3 `prod-eu`

路径：`/opt/scopeslab-api/.env`

```env
ENV=production
PROJECT_NAME=scopeslab-api-prod-eu
API_V1_STR=/api/v1
API_PORT=8100

DATABASE_URL=postgresql+asyncpg://crawler_api:replace-with-password@127.0.0.1:5432/crawler
DATA_REGION=EU

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-redis-password

SECRET_KEY=replace-with-long-random-secret
API_AUTH_MODE=aksk
API_KEYS_JSON={"partner-prod-eu":{"secret":"replace-with-secret","enabled":true}}
API_SIGNATURE_TTL_SECONDS=300
```

### 4.4 `prod-sg`

路径：`/opt/scopeslab-api/.env`

```env
ENV=production
PROJECT_NAME=scopeslab-api-prod-sg
API_V1_STR=/api/v1
API_PORT=8101

DATABASE_URL=postgresql+asyncpg://crawler_api_sg:replace-with-password@127.0.0.1:5432/crawler-sg
DATA_REGION=SG

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-redis-password

SECRET_KEY=replace-with-long-random-secret
API_AUTH_MODE=aksk
API_KEYS_JSON={"partner-prod-sg":{"secret":"replace-with-secret","enabled":true}}
API_SIGNATURE_TTL_SECONDS=300
```

## 5. GitHub Actions 发布

测试环境 runner label：

```text
scopeslab-api-test
```

产线 runner label：

```text
scopeslab-api-prod-eu
scopeslab-api-prod-sg
```

测试环境发布：

```bash
git push origin test
```

手动测试发布：

```text
GitHub -> Actions -> scopeslab-api Test Build And Publish -> Run workflow
deploy_region=eu/sg/all
target_ref=test、tag 或 commit
```

产线发布：

```bash
git push origin main
```

手动产线发布：

```text
GitHub -> Actions -> scopeslab-api Prod Build And Publish -> Run workflow
deploy_region=eu/sg/all
target_ref=main、tag 或 commit
```

## 6. 手动部署

手动部署使用同一个脚本：

```bash
cd <fastapi-template-repo>
scripts/deploy_api.sh test
scripts/deploy_api.sh test-sg
scripts/deploy_api.sh prod-eu
scripts/deploy_api.sh prod-sg
```

脚本会同步代码、执行 compose 启动并做健康检查。

## 7. 启动命令

如果已经在目标目录内，也可以直接启动：

```bash
cd /opt/scopeslab-api
docker compose -p scopeslab-api-test --env-file .env up -d --build app
```

按目标替换 compose project：

```text
test     -> scopeslab-api-test
test-sg  -> scopeslab-api-test-sg
prod-eu  -> scopeslab-api-prod-eu
prod-sg  -> scopeslab-api-prod-sg
```

最小部署只启动 `app`。PostgreSQL、Redis、nginx 使用服务器已有服务。

## 8. 发布后检查

查看容器：

```bash
docker compose -p scopeslab-api-test --env-file .env ps
docker compose -p scopeslab-api-test --env-file .env logs --tail 100 app
```

本机健康检查：

```bash
curl -i http://127.0.0.1:8110/api/v1/config/health
curl -i http://127.0.0.1:8111/api/v1/config/health
curl -i http://127.0.0.1:8100/api/v1/config/health
curl -i http://127.0.0.1:8101/api/v1/config/health
```

期望 `database` 和 `redis` 都是 `up`。

外部域名检查：

```bash
curl -i https://api-test.example.com/api/v1/config/health
curl -i https://api-test-sg.example.com/api/v1/config/health
```

公告接口使用 AK/SK 签名，请按 [CRAWLER_NOTICES_API_APIFOX.md](CRAWLER_NOTICES_API_APIFOX.md) 验证。

## 9. Nginx

nginx 示例见 [NGINX_API_PROXY_EXAMPLE.md](NGINX_API_PROXY_EXAMPLE.md)。

修改 nginx 后：

```bash
sudo nginx -t
sudo systemctl reload nginx
```
