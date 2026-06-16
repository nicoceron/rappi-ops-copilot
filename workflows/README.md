# n8n Workflows

Import `rappi_ops_chat_agent.json` into n8n after starting the local stack, or
run this from the repository root to import the workflow and credentials:

```bash
python3 scripts/setup_n8n.py --activate
```

## Local URLs

- n8n: `http://localhost:5678`
- Ops API from host: `http://localhost:8000`
- Ops API from n8n container: `http://ops-api:8000`

## Required n8n Credentials

`scripts/setup_n8n.py` creates or updates these credentials from `.env`.
If importing manually, create them in n8n after import:

- `DeepSeek account`: DeepSeek API credential with your API key.
- `Rappi Ops Postgres`: Postgres credential pointing to the `postgres` service.

For the Docker Compose defaults:

- Host: `postgres`
- Port: `5432`
- Database: `rappi_ops`
- User: `rappi`
- Password: `rappi`

## Notes

The workflow uses the DeepSeek Chat Model node with `deepseek-v4-pro`.
If your n8n version does not yet expose the current DeepSeek V4 controls, keep the analytics API as-is and update only the chat model node when n8n releases support for the missing parameters.

If the chat webhook returns `{"message":"Error in workflow"}` before the Ops API
logs a request, check the latest n8n execution. A DeepSeek HTTP `402` means the
credential is valid enough to reach DeepSeek, but the account needs available
balance or billing enabled before the agent can answer.
