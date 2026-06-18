# Slack Integration Setup

Connect engg-intelligence to your Slack workspace to collect message activity
signals used in team health scoring.

---

## Overview

engg-intelligence uses a Slack **bot token** (not OAuth user token) to read
channel history in batch during the nightly run. No webhook or real-time
event subscription is required.

---

## Step 1 — Create a Slack App

1. Open https://api.slack.com/apps and click **Create New App**.
2. Choose **From scratch** (not App Directory listing).
3. Give it a name — e.g. `engg-intelligence` — and select your workspace.
4. Click **Create App**.

> Create this as an **Internal Integration** (internal app). Do not publish
> to the Slack App Directory unless you are deploying across multiple external
> workspaces (see the note at the end of this guide).

---

## Step 2 — Configure OAuth scopes

Navigate to **OAuth & Permissions** in the left sidebar.

Under **Bot Token Scopes**, add these scopes:

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read messages in public channels |
| `channels:read` | List public channels and their metadata |
| `groups:history` | Read messages in private channels the bot is invited to |
| `groups:read` | List private channels the bot belongs to |
| `users:read` | Look up user display names for identity resolution |
| `users:read.email` | *(optional)* Look up user emails for identity resolution |

> `users:read.email` may require workspace admin approval. See the fallback
> section below if this scope is denied.

---

## Step 3 — Install the app to your workspace

1. On the **OAuth & Permissions** page, click **Install to Workspace**.
2. Review the requested permissions and click **Allow**.
3. Copy the **Bot User OAuth Token** — it starts with `xoxb-`.

---

## Step 4 — Get the signing secret

1. In the left sidebar, click **Basic Information**.
2. Under **App Credentials**, copy the **Signing Secret**.

---

## Step 5 — Enter credentials in the Admin UI

1. Open engg-intelligence at your configured `APP_URL`.
2. Log in as an admin.
3. Navigate to **Admin → Integrations → Slack**.
4. Enter:
   - **Bot Token**: the `xoxb-…` token from Step 3
   - **Signing Secret**: the secret from Step 4
5. Click **Save & Test Connection**.

A successful test shows the workspace name and confirms the bot can list channels.

---

## Fallback when `users:read.email` is denied

If your Slack workspace admin denies the `users:read.email` scope:

- engg-intelligence falls back to **display name fuzzy matching** using the
  `pg_trgm` PostgreSQL extension.
- Identity resolution matches Slack display names to Keka/GitHub usernames
  using trigram similarity (threshold: 0.6).
- This approach works well for teams with consistent naming conventions (e.g.
  `firstname.lastname` everywhere).
- Accuracy is lower for teams with nicknames, initials, or inconsistent casing.

To improve matching without `users:read.email`:
- Ensure all engineers use the same display name format in Slack, GitHub, and Keka.
- Use the **Admin → Identity Mappings** screen to manually link any unresolved users.

---

## Inviting the bot to private channels (optional)

By default, the bot only reads **public** channels. To include private channels:

1. Open the private channel in Slack.
2. Type `/invite @engg-intelligence` (or whatever you named the bot).
3. The bot will begin collecting activity from that channel on the next nightly run.

---

## Note on external workspace deployments

If you are deploying engg-intelligence as a product serving **multiple external
organisations** (i.e. each customer connects their own Slack workspace):

- You must initiate a **Slack App Review** at https://api.slack.com/start/distributing
- Add a Privacy Policy URL and support contact in the App settings.
- The `users:read.email` scope requires justification during review.
- App Review typically takes 1–4 weeks.

For single-workspace internal deployments, App Review is **not required**.
