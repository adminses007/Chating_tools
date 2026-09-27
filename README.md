# Chat System

中心化聊天：**Client → Server → Client**（非 P2P / 非自动发现）。

- Server：FastAPI + WebSocket + SQLite + 文件服务 + Admin
- Client：Python + HTML/CSS/JS（pywebview / 浏览器）
- 同一套程序支持办公室 LAN（无 Internet）与 VPS

## 功能进度

- [x] Phase 1：Server 基础（config / SQLite / `/health`）
- [x] Phase 2：用户系统（注册 / 登录 / JWT / bcrypt）
- [x] Phase 3：Client（Server 地址 / 登录 UI / WebSocket）
- [x] Phase 4：私聊（用户列表 / 消息落库 / 状态）
- [x] Phase 5：离线未读 / 重连同步
- [x] Phase 6：文件传输（上传进度 / 下载 / 图片预览）
- [x] Phase 7：群聊（创建 / 成员 / 退出）
- [x] Phase 8：Admin Dashboard（`/admin`，默认不读私聊正文）
- [x] Phase 9：安全加固（哈希 / JWT / 限流 / 路径与类型校验）
- [x] Phase 10：Windows 打包脚本（PyInstaller）

## 快速开始

```bash
pip install -r requirements.txt
start_server.bat
# 另开窗口
start_client.bat
```

或：

```bash
python -m server.main
python -m client.main
```

默认 Server：`http://127.0.0.1:8000`  
聊天页面（电脑 / 手机浏览器）：`http://127.0.0.1:8000/`  
Health：`GET /health`  
Admin：`http://127.0.0.1:8000/admin`

**首个注册用户自动成为 admin。**  
自助注册必须填写邀请码（默认见 `config/server.json` → `register_invite_code`）。

### 手机通过 IP 使用

1. 电脑启动 Server（监听 `0.0.0.0:8000`）
2. 手机与 Server 同一局域网
3. 手机浏览器打开：`http://服务器局域网IP:8000`  
   例如：`http://192.168.1.100:8000`
4. 填写邀请码后注册 / 登录（无需安装 App）

Windows 防火墙需放行入站 TCP 8000。

## 配置

`config/server.json` — host/port/database/file_storage/max_file_size/jwt_secret  
`config/client.json` — server_url（客户端也可在 UI 修改）

## LAN 部署

1. 服务器电脑运行 `start_server.bat`（监听 `0.0.0.0:8000`）
2. 防火墙放行 8000
3. 电脑客户端：`start_client.bat`，或浏览器打开 `http://服务器IP:8000`
4. 手机：浏览器打开 `http://服务器IP:8000`
5. 无 Internet 只要局域网互通即可

## VPS 部署

同一代码部署到 Ubuntu 等 VPS，运行 Uvicorn。生产建议 Nginx + HTTPS。客户端将 Server 地址改为 `https://chat.example.com`。

## 测试清单

### Health
```bash
curl http://127.0.0.1:8000/health
```

### 注册 / 登录
```bash
curl -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret1\",\"display_name\":\"Alice\",\"invite_code\":\"abc888#\"}"
curl -X POST http://127.0.0.1:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret1\"}"
```

### 客户端
1. 启动 Client，确认 Server Address
2. 用 Alice / Bob 分别登录两个客户端
3. 私聊、离线重连、发文件、建群
4. 浏览器打开 `/admin` 用 Alice（admin）查看状态

## Windows 打包

```bash
python build_windows.py
# 或 build_windows.bat
```

产物：`dist/Server.exe`、`dist/LANChat.exe`  
说明见 [PACKAGING.md](PACKAGING.md)

## 自动化冒烟测试

```bash
python -m server.main
# 另开终端
python scripts/smoke_test.py
python scripts/ws_smoke_test.py
```

## 目录结构

```
server/   FastAPI 服务端
client/   桌面客户端
shared/   共用 schemas
config/   配置文件
data/     SQLite 与上传文件
```

## 安全说明

- 密码 bcrypt 哈希，不明文存储
- JWT access + 可撤销 refresh session
- WebSocket 需 token
- 文件类型白名单、大小限制、存储路径隔离
- API 简易 IP 速率限制
- Admin 默认仅消息元数据，不含私聊正文
