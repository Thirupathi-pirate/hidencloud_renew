# HidenCloud Auto Renew (Python Version)

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

HidenCloud auto-renewal and payment script written in Python, designed for GitHub Actions.

✨ **Core Highlights:**

- Auto-renewal + auto-payment
- Uses Infinicloud (WebDAV) for Cookie persistence
- Supports **QingLong-style multi-channel notifications**
- Uses **single channel selection** at runtime
- **Default channel: wxpusher**
- Chinese logs and notification content processed in **UTF-8** to minimize encoding issues

---

## Features

- **Auto-renewal**: Automatically detect services and extend validity
- **Auto-payment**: Automatically identify and pay invoices after renewal
- **Cookie Persistence**:
  - Automatically upload latest Cookie to Infinicloud (WebDAV)
  - Script reads cloud cache on startup to reduce Cookie expiry impact
- **Single Notification Channel**:
  - Default: `wxpusher`
  - Supports QingLong-style notification channels:
    - `wxpusher`
    - `serverchan`
    - `telegram`
    - `dingtalk`
    - `wework_bot`
    - `wework_app`
    - `feishu`
    - `bark`
    - `pushplus`
    - `gotify`
    - `gocqhttp`
    - `pushdeer`
    - `chat`
    - `aibotk`
    - `igot`
    - `weplusbot`
    - `email`
    - `pushme`
    - `webhook`
    - `chronocat`
    - `ntfy`
- **Multi-account support**: Batch run across multiple accounts
- **Failure retry**: Supports GitHub Actions re-run on failure

---

## Deployment Guide

### 1. Prerequisites

- GitHub account
- HidenCloud account
- Infinicloud account: for storing Cookie JSON file
- At least one notification channel account/bot configuration (default: wxpusher)

### 2. Getting HidenCloud Cookie

1. Open HidenCloud console in your browser and log in
2. Press `F12` to open developer tools, switch to **Network**
3. Refresh the page, click any authenticated request
4. Copy the full `Cookie` from the request headers

### 3. Getting Infinicloud WebDAV Info

1. Log in to Infinicloud
2. Go to **My Page**
3. Enable **Apps Connection**
4. Note down:
   - `WEBDAV_URL`
   - `WEBDAV_USER`
   - `WEBDAV_PASS`

---

## Notification Setup

### Operating Mode

- Only sends via **one** notification channel
- Channel specified via `NOTIFY_CHANNEL`
- **Defaults to `wxpusher` when `NOTIFY_CHANNEL` is not set**

### Channel Selection Examples

Set `NOTIFY_CHANNEL` to any of the following values:

| Value | Description |
|---|---|
| `wxpusher` | Default channel |
| `serverchan` | Server Chan |
| `telegram` | Telegram Bot |
| `dingtalk` | DingTalk Bot |
| `wework_bot` | WeCom Bot |
| `wework_app` | WeCom App |
| `feishu` | Feishu Bot |
| `bark` | Bark |
| `pushplus` | PushPlus |
| `gotify` | Gotify |
| `gocqhttp` | go-cqhttp |
| `pushdeer` | PushDeer |
| `chat` | Synology Chat |
| `aibotk` | AiBotk |
| `igot` | iGot |
| `weplusbot` | WePlusBot |
| `email` | SMTP Email |
| `pushme` | PushMe |
| `webhook` | Custom Webhook |
| `chronocat` | Chronocat |
| `ntfy` | ntfy |

> It is recommended to put `NOTIFY_CHANNEL` in GitHub **Repository Variables** and all other sensitive values in **Repository Secrets**.

### WxPusher Compatibility

This project supports two sets of WxPusher variables:

- **Legacy project variables**
  - `WP_APP_TOKEN_ONE`
  - `WP_UIDs`
- **QingLong-style variables**
  - `WXPUSHER_APP_TOKEN`
  - `WXPUSHER_TOPIC_IDS`
  - `WXPUSHER_UIDS`

If you were already using this project's WxPusher configuration, **you can continue using it without changes after upgrading**.

---

## GitHub Actions Configuration

### 1. Required Configuration

#### Repository Secrets

| Name | Required | Description |
|---|:---:|---|
| `HIDEN_COOKIE` | ✅ | Initial Cookie. Separate multiple accounts with newline or `&` |
| `WEBDAV_URL` | ✅ | Infinicloud WebDAV URL |
| `WEBDAV_USER` | ✅ | Infinicloud username |
| `WEBDAV_PASS` | ✅ | Infinicloud password |

#### Repository Variables

| Name | Required | Description |
|---|:---:|---|
| `NOTIFY_CHANNEL` | ❌ | Selected notification channel; defaults to `wxpusher` |

### 2. Channel Configurations

Only configure the variables for **your selected channel**.

#### wxpusher

| Name | Description |
|---|---|
| `WP_APP_TOKEN_ONE` | Legacy app token |
| `WP_UIDs` | Legacy UIDs, separate multiple with `;` |
| `WXPUSHER_APP_TOKEN` | QingLong-style app token |
| `WXPUSHER_TOPIC_IDS` | Topic IDs, separate multiple with `;` |
| `WXPUSHER_UIDS` | UIDs, separate multiple with `;` |

#### Server Chan

| Name | Description |
|---|---|
| `PUSH_KEY` | QingLong standard variable |
| `SERVERCHAN_SENDKEY` | Compatibility alias |

#### Telegram

| Name | Description |
|---|---|
| `TG_BOT_TOKEN` | Bot Token |
| `TG_CHAT_ID` | Recommended |
| `TG_USER_ID` | Legacy format (for compatibility) |
| `TG_API_HOST` | Optional, custom API Host |
| `TG_PROXY_AUTH` / `TG_PROXY_HOST` / `TG_PROXY_PORT` | Optional, proxy configuration |

#### DingTalk

| Name | Description |
|---|---|
| `DD_BOT_TOKEN` | Bot Token |
| `DD_BOT_SECRET` | Optional, signing secret |

#### WeCom Bot

| Name | Description |
|---|---|
| `QYWX_KEY` | Bot key |
| `QYWX_ORIGIN` | Optional, WeCom proxy URL |

#### WeCom App

| Name | Description |
|---|---|
| `QYWX_AM` | `corpid,corpsecret,touser,agentid[,media_id]` |
| `QYWX_ORIGIN` | Optional, WeCom proxy URL |

#### Feishu

| Name | Description |
|---|---|
| `FEISHU_WEBHOOK` | Direct webhook URL |
| `FEISHU_SECRET` | Optional, signing secret |
| `FSKEY` | Compatibility with legacy QingLong variable |
| `FSSECRET` | Compatibility with legacy QingLong variable |

#### Bark

| Name | Description |
|---|---|
| `BARK_PUSH` | Bark URL or device code |
| `BARK_ARCHIVE` / `BARK_GROUP` / `BARK_SOUND` / `BARK_ICON` / `BARK_LEVEL` / `BARK_URL` | Optional parameters |

#### PushPlus

| Name | Description |
|---|---|
| `PUSH_PLUS_TOKEN` | QingLong standard variable |
| `PUSHPLUS_TOKEN` | Compatibility alias |
| `PUSH_PLUS_USER` | Group code |
| `PUSH_PLUS_TEMPLATE` | Template type |
| `PUSH_PLUS_CHANNEL` | Channel |
| `PUSH_PLUS_WEBHOOK` | Webhook code |
| `PUSH_PLUS_CALLBACKURL` | Callback URL |
| `PUSH_PLUS_TO` | Friend token / WeCom user ID |

#### Other Channels

| Channel | Variables |
|---|---|
| `gotify` | `GOTIFY_URL` `GOTIFY_TOKEN` `GOTIFY_PRIORITY` |
| `gocqhttp` | `GOBOT_URL` `GOBOT_QQ` `GOBOT_TOKEN` |
| `pushdeer` | `DEER_KEY` / `PUSHDEER_KEY`, optional `DEER_URL` |
| `chat` | `CHAT_URL` `CHAT_TOKEN` |
| `aibotk` | `AIBOTK_KEY` `AIBOTK_TYPE` `AIBOTK_NAME` |
| `igot` | `IGOT_PUSH_KEY` |
| `weplusbot` | `WE_PLUS_BOT_TOKEN` `WE_PLUS_BOT_RECEIVER` `WE_PLUS_BOT_VERSION` |
| `email` | `SMTP_SERVER` `SMTP_SSL` `SMTP_EMAIL` `SMTP_PASSWORD` `SMTP_NAME`, optional `SMTP_TO_EMAIL` |
| `pushme` | `PUSHME_KEY`, optional `PUSHME_URL` |
| `webhook` | `WEBHOOK_URL` `WEBHOOK_METHOD` `WEBHOOK_BODY` `WEBHOOK_HEADERS` `WEBHOOK_CONTENT_TYPE` |
| `chronocat` | `CHRONOCAT_QQ` `CHRONOCAT_TOKEN` `CHRONOCAT_URL` |
| `ntfy` | `NTFY_URL` `NTFY_TOPIC`, optional `NTFY_PRIORITY` `NTFY_TOKEN` `NTFY_USERNAME` `NTFY_PASSWORD` `NTFY_ACTIONS` |

---

## Getting Started

1. Fork this project
2. Configure `Secrets` and `Variables`
3. Open **Actions** in your GitHub repository
4. Select **HidenCloud Auto Renew (Python)**
5. Click **Run workflow**
6. Verify:
   - Whether `hiden_cookies.json` was created in Infinicloud
   - Whether the notification was delivered successfully

The script runs on a GitHub Actions schedule by default and will retry after a delay on failure.

---

## File Structure

```text
.
├── .github/workflows/
│   ├── cron.yml
│   └── main.yml
├── main.py
├── notify.py
├── requirements.txt
├── tests/
│   └── test_notify.py
└── README.md
```

---

## Encoding and Chinese Output

The project handles Chinese content in UTF-8:

- Python files use UTF-8
- In GitHub Actions, set:
  - `PYTHONUTF8=1`
  - `PYTHONIOENCODING=UTF-8`
- Notification JSON/text body is sent in UTF-8 where possible

---

## Disclaimer

1. This project is for educational purposes only, do not use for illegal activities
2. The script involves account operations; the author is not responsible for any resulting losses
3. Please safeguard your Secrets and Variables
4. It is recommended to regularly check Cookie status and notification configuration

---

If this project helped you, feel free to give it a Star ⭐
