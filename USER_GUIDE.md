# LAN Chat — User Guide (English)

Centralized chat: **Client → Server → Client**.  
Use it on a PC (desktop app or browser) or on a phone browser on the same network.

---

## Before you start

1. Make sure the **chat server is running**.
2. Open the app in one of these ways:
   - **Desktop client:** run `LANChat.exe` / `start_client.bat`
   - **PC browser:** open `http://SERVER_IP:8000`
   - **Phone browser (same Wi‑Fi/LAN):** open `http://SERVER_IP:8000`  
     Example: `http://192.168.1.100:8000`
3. On the login screen, check **Server Address** (desktop client).  
   Tap **Test Connection** — status should become connected before you register or log in.  
   (If you opened the page from the server URL in a browser, the address is already set.)

---

## Registration (create an account)

Self-registration requires an **invite code** from your admin.

### Steps

1. On the welcome screen, tap **Register**.
2. Fill in the fields:

   | Field | Rules |
   |---|---|
   | **Username** | 3–64 characters; used to log in |
   | **Display name** | Name shown to others in chat |
   | **Password** | At least **6** characters |
   | **Invite code** | **`abc888#`** (default; ask admin if it was changed) |

3. Tap **Create Account**.
4. If registration succeeds, you are logged in and enter the chat screen.

### Notes

- Default invite code: **`abc888#`** (configured in `config/server.json` → `register_invite_code`).
- Wrong invite code → registration is rejected.
- Username already taken → choose another username.
- The **first** user who registers on a new server becomes **admin**.

---

## Login

### Steps

1. On the welcome screen, tap **Login**.
2. Enter your **Username** and **Password**.
3. Optional:
   - **Remember username** — saves your username on this device
   - **Remember password** — saves your password on this device (use only on a trusted personal device)
4. Tap **Enter Chat**.

### If login fails

- Check username and password (caps lock, wrong account).
- Confirm the **Server Address** / network (phone must be on the same LAN as the server, unless you use a public VPS URL).
- Ask admin if your account was disabled.

---

## After you are in

- **Contacts** — open a user to start a private chat.
- **Recent Chats** — reopen conversations; unread badges clear when you open a chat.
- Send text, images, video, audio, and files (size limits follow server config).
- Create or join **group** chats from the chat UI.
- Language switch on the login screen: **中文** / **မြန်မာ**.

### Logout

Use the logout / exit control in the app header (or close the client).  
On a shared computer, do not enable “Remember password”.

---

## Admin (operators only)

- Admin dashboard: `http://SERVER_IP:8000/admin`
- Default login: username **`admin`**, password **`abc888#`**
- In **Users** tab: create / disable / reset password / **Delete** accounts
- You cannot delete your own account or the last remaining admin
- Admins can see system status; private message content is not shown by default

---

## Quick checklist

| Task | What you need |
|---|---|
| Register | Server online + invite code **`abc888#`** + username + display name + password (≥6) |
| Login | Server online + username + password |
| Phone use | Same LAN (or VPS URL) + browser → `http://SERVER_IP:8000` |
| Firewall | Server PC allows inbound TCP **8000** |

---

## Need help?

- Health check: `GET http://SERVER_IP:8000/health`
- Default invite code: **`abc888#`** (confirm with admin if changed). Ask admin for the server IP/URL.
- See also: [README.md](README.md) (setup) · [PACKAGING.md](PACKAGING.md) (Windows build)
