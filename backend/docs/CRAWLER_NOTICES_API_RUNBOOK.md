# 公告查询 API 运维手册

本文记录部署之外的运维、runner、网络、排障和回滚。部署操作见 [CRAWLER_NOTICES_API_DEPLOYMENT.md](CRAWLER_NOTICES_API_DEPLOYMENT.md)。

## 1. Runner

推荐 runner labels：

```text
test/test-sg -> self-hosted, scopeslab-api-test
prod-eu      -> self-hosted, scopeslab-api-prod-eu
prod-sg      -> self-hosted, scopeslab-api-prod-sg
```

repo-level runner 只属于当前仓库。`fastapi-template` 仓库需要自己的 runner，除非使用已授权给该仓库的 organization-level runner。

同一台服务器可以运行多个 runner 实例，但目录必须不同。例如：

```text
/opt/actions-runner-api-test
```

runner 服务命令：

```bash
cd /opt/actions-runner-api-test
sudo ./svc.sh status
sudo ./svc.sh start
sudo ./svc.sh stop
```

如果 `config.sh` 访问 GitHub 报 SSL 错误，先清理当前 shell 里的代理变量：

```bash
unset HTTPS_PROXY HTTP_PROXY ALL_PROXY https_proxy http_proxy all_proxy
```

## 2. Workflow

workflow 文件：

```text
.github/workflows/test.yml
.github/workflows/prod.yml
```

workflow 调用统一部署脚本：

```bash
scripts/deploy_api.sh <target>
```

脚本做这些事：

- 校验 target
- 校验部署目录和 `.env`
- `rsync` 同步代码，不覆盖 `.env` 和日志
- `docker compose up -d --build app`
- 调用 `/api/v1/config/health`

## 3. 网络

API 容器需要访问：

- PostgreSQL `5432`
- Redis `6379`
- 宿主机 nginx 访问 `127.0.0.1:${API_PORT}`

查看 Docker 网络：

```bash
docker network ls | grep scopeslab-api
docker network inspect scopeslab-api-test_app-network \
  --format '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}}{{end}}'
```

测试环境同时部署 `test` 和 `test-sg` 时，两个 compose project 可能有不同网段，都要放行。

UFW 示例：

```bash
sudo ufw allow from <api_docker_subnet> to any port 5432 proto tcp
sudo ufw allow from <api_docker_subnet> to any port 6379 proto tcp
sudo ufw reload
sudo ufw status
```

PostgreSQL `pg_hba.conf` 示例：

```text
host crawler    crawler_api    <api_docker_subnet> scram-sha-256
host crawler-sg crawler_api_sg <api_docker_subnet> scram-sha-256
```

查找 `pg_hba.conf`：

```bash
sudo -u postgres psql -c "SHOW hba_file;"
```

reload PostgreSQL：

```bash
sudo systemctl reload postgresql
```

或：

```bash
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

## 4. 连通性验证

容器内 TCP 验证：

```bash
docker compose -p scopeslab-api-test --env-file .env run --rm app \
  python -c "import socket; socket.create_connection(('192.168.88.151', 5432), 5); print('pg tcp ok')"

docker compose -p scopeslab-api-test --env-file .env run --rm app \
  python -c "import socket; socket.create_connection(('192.168.88.151', 6379), 5); print('redis tcp ok')"
```

健康检查：

```bash
curl -i http://127.0.0.1:${API_PORT}/api/v1/config/health
```

## 5. 日志

查看应用日志：

```bash
docker compose -p scopeslab-api-test --env-file .env logs --tail 100 app
docker compose -p scopeslab-api-test --env-file .env logs -f app
```

查看 nginx 日志：

```bash
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
```

## 6. 回滚

使用 GitHub Actions 手动选择旧 commit/tag 发布，或在服务器上执行：

```bash
cd /opt/scopeslab-api
git checkout <previous_commit_or_tag>
docker compose -p scopeslab-api-test --env-file .env up -d --build app
curl -i http://127.0.0.1:8110/api/v1/config/health
```

如果只是 `.env` 配错，修正后重启：

```bash
docker compose -p scopeslab-api-test --env-file .env restart app
```

## 7. 常见问题

### 7.1 health 返回 database down

检查：

```bash
grep -E 'DATABASE_URL|DATA_REGION' .env
docker compose -p scopeslab-api-test --env-file .env logs --tail 100 app
```

重点看：

- `DATABASE_URL` 是否是 `postgresql+asyncpg://`
- 用户、密码、库名是否正确
- Docker 网段是否已在 UFW 和 `pg_hba.conf` 放行

### 7.2 health 返回 redis down

检查：

```bash
grep -E 'REDIS_HOST|REDIS_PORT|REDIS_PASSWORD' .env
docker compose -p scopeslab-api-test --env-file .env logs --tail 100 app
```

Redis 不可用时，AK/SK nonce 防重放不可用，公告接口会拒绝请求。

### 7.3 接口返回 403

通常是跨区查询：

```text
DATA_REGION=EU 只允许 FRA/BEL/DEU/NLD/ITA/ESP
DATA_REGION=SG 只允许 SGP
```

### 7.4 接口返回空列表

检查数据库：

```sql
SELECT data_region, country_code, count(*)
FROM crawler_notices
GROUP BY data_region, country_code
ORDER BY data_region, country_code;
```

接口入参是三位码，例如 `DEU`；库里是二位码，例如 `DE`。
