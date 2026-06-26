# Skill: Ticket Fetcher

Use this skill when a work item contains a URL to a Jira or ClickUp ticket.
Fetch the ticket content and return it as structured text for the orchestrator.

## Detecting a ticket URL

- Jira URL pattern: `https://[domain].atlassian.net/browse/[KEY]-[number]`
- ClickUp URL pattern: `https://app.clickup.com/t/[id]` or `https://[team].clickup.com/[id]`
- If the work item is plain text (not a URL), skip this skill entirely.

## Fetching a Jira ticket

```bash
curl -s \
  -H "Authorization: Bearer $JIRA_API_TOKEN" \
  -H "Accept: application/json" \
  "https://[domain].atlassian.net/rest/api/3/issue/[KEY]-[number]"
```

Extract from the response:
- `fields.summary` — ticket title
- `fields.description` — ticket description (may be Atlassian Document Format — extract plain text)
- `fields.issuetype.name` — Bug, Story, Task, etc.
- `fields.priority.name` — priority level
- `fields.acceptance_criteria` or custom field — acceptance criteria if present

## Fetching a ClickUp ticket

```bash
curl -s \
  -H "Authorization: $CLICKUP_API_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.clickup.com/api/v2/task/[task_id]"
```

Extract from the response:
- `name` — ticket title
- `description` — ticket description
- `status.status` — current status
- `priority.priority` — priority level
- `custom_fields` — look for acceptance criteria fields

## Output format

Return a structured block to the orchestrator:

```
## Ticket: [KEY]-[number] / [task_id]
Type: [Bug / Feature / Task]
Title: [title]
Priority: [priority]
URL: [original URL]

### Description
[description text]

### Acceptance criteria
[list of criteria, or "Not specified" if absent]
```

## Authentication failure handling

If `JIRA_API_TOKEN` or `CLICKUP_API_TOKEN` is not set, or the API returns 401/403:

```
Ticket fetch failed: [JIRA/CLICKUP]_API_TOKEN not set or invalid.

To configure:
  export JIRA_API_TOKEN=your_token_here       # Jira Personal Access Token
  export CLICKUP_API_TOKEN=your_token_here    # ClickUp Personal API Token

Alternatively, paste the ticket content directly and I will continue.
```

Wait for the user to either set the token or paste the content before proceeding.

## Notes

- Never log or display the API token value
- If the ticket is not found (404), report: "Ticket [ID] not found. Please check the URL."
- If the description is empty, proceed with the title only and flag it in clarifying questions
