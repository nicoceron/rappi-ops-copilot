"""Provision local n8n credentials and import the Rappi Ops workflow.

The script reads secrets from .env, writes temporary import files outside the
repository, and imports them with the n8n CLI running inside Docker Compose.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "rappi_ops_chat_agent.json"
ENV_PATH = ROOT / ".env"
DEEPSEEK_CREDENTIAL_NAME = "DeepSeek account"
POSTGRES_CREDENTIAL_NAME = "Rappi Ops Postgres"
DEFAULT_CREDENTIAL_IDS = {
    DEEPSEEK_CREDENTIAL_NAME: "rappiDeepSeek001",
    POSTGRES_CREDENTIAL_NAME: "rappiOpsPostgres",
}
WORKFLOW_NAME = "Rappi Ops Copilot - DeepSeek Chat Agent"
DEFAULT_WORKFLOW_ID = "rappiOpsAgent001"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def run(command: list[str], *, capture: bool = False) -> str:
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if process.returncode != 0:
        detail = ""
        if capture:
            detail = f"\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        raise RuntimeError(f"Command failed: {' '.join(command)}{detail}")
    return process.stdout if capture else ""


def parse_json_output(output: str) -> Any:
    text = output.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for start, character in enumerate(text):
            if character not in "[{":
                continue
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                continue
        raise


def as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    raise TypeError(f"Expected JSON object or list, got {type(value).__name__}")


def export_credentials() -> list[dict[str, Any]]:
    output = run(
        ["docker", "compose", "exec", "-T", "n8n", "n8n", "export:credentials", "--all", "--pretty"],
        capture=True,
    )
    return as_list(parse_json_output(output))


def export_workflows() -> list[dict[str, Any]]:
    output = run(
        ["docker", "compose", "exec", "-T", "n8n", "n8n", "export:workflow", "--all", "--pretty"],
        capture=True,
    )
    return as_list(parse_json_output(output))


def copy_into_n8n(source: Path, target: str) -> None:
    run(["docker", "compose", "cp", str(source), f"n8n:{target}"])


def import_credentials(path: Path) -> None:
    target = "/tmp/rappi_ops_credentials_import.json"
    copy_into_n8n(path, target)
    run(["docker", "compose", "exec", "-T", "n8n", "n8n", "import:credentials", "--input", target])


def import_workflow(path: Path) -> None:
    target = "/tmp/rappi_ops_workflow_import.json"
    copy_into_n8n(path, target)
    command = ["docker", "compose", "exec", "-T", "n8n", "n8n", "import:workflow", "--input", target]
    run(command)


def set_workflow_active(workflow_id: str) -> None:
    run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "n8n",
            "n8n",
            "publish:workflow",
            "--id",
            workflow_id,
        ]
    )


def restart_n8n() -> None:
    run(["docker", "compose", "restart", "n8n"])


def get_workflow_id(workflows: list[dict[str, Any]]) -> str:
    workflow = next((item for item in workflows if item.get("name") == WORKFLOW_NAME), None)
    if not workflow or not workflow.get("id"):
        raise RuntimeError(f"Could not find imported workflow '{WORKFLOW_NAME}'")
    return str(workflow["id"])


def credential_payload(existing: list[dict[str, Any]], env: dict[str, str]) -> list[dict[str, Any]]:
    by_name = {item.get("name"): item for item in existing}
    deepseek_key = env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required in .env or the shell environment")

    credentials: list[dict[str, Any]] = [
        {
            "name": DEEPSEEK_CREDENTIAL_NAME,
            "type": "deepSeekApi",
            "data": {
                "apiKey": deepseek_key,
                "url": "https://api.deepseek.com",
            },
        },
        {
            "name": POSTGRES_CREDENTIAL_NAME,
            "type": "postgres",
            "data": {
                "host": "postgres",
                "database": env.get("POSTGRES_DB", "rappi_ops"),
                "user": env.get("POSTGRES_USER", "rappi"),
                "password": env.get("POSTGRES_PASSWORD", "rappi"),
                "port": 5432,
                "ssl": "disable",
                "allowUnauthorizedCerts": False,
                "maxConnections": 100,
            },
        },
    ]

    for credential in credentials:
        current = by_name.get(credential["name"])
        if current and current.get("id"):
            credential["id"] = current["id"]
        else:
            credential["id"] = DEFAULT_CREDENTIAL_IDS[credential["name"]]

    return credentials


def workflow_payload(
    credentials: list[dict[str, Any]],
    workflows: list[dict[str, Any]],
    *,
    activate: bool,
) -> dict[str, Any]:
    by_credential_name = {item.get("name"): item for item in credentials}
    deepseek_id = by_credential_name.get(DEEPSEEK_CREDENTIAL_NAME, {}).get("id")
    postgres_id = by_credential_name.get(POSTGRES_CREDENTIAL_NAME, {}).get("id")
    if not deepseek_id or not postgres_id:
        raise RuntimeError("Expected DeepSeek and Postgres credentials to exist after import")

    workflow = json.loads(WORKFLOW_PATH.read_text())
    existing_workflow = next((item for item in workflows if item.get("name") == WORKFLOW_NAME), None)
    if existing_workflow and existing_workflow.get("id"):
        workflow["id"] = existing_workflow["id"]
    else:
        workflow["id"] = DEFAULT_WORKFLOW_ID

    workflow["active"] = activate
    workflow.setdefault("meta", {})["templateCredsSetupCompleted"] = True

    for node in workflow.get("nodes", []):
        node_credentials = node.get("credentials") or {}
        if "deepSeekApi" in node_credentials:
            node_credentials["deepSeekApi"]["id"] = deepseek_id
            node_credentials["deepSeekApi"]["name"] = DEEPSEEK_CREDENTIAL_NAME
        if "postgres" in node_credentials:
            node_credentials["postgres"]["id"] = postgres_id
            node_credentials["postgres"]["name"] = POSTGRES_CREDENTIAL_NAME

    return workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local n8n credentials and workflow.")
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Import the workflow as active so the production chat webhook is available.",
    )
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    with tempfile.TemporaryDirectory(prefix="rappi-ops-n8n-") as temp_dir:
        temp = Path(temp_dir)
        existing_credentials = export_credentials()
        credentials_path = temp / "credentials.json"
        credentials_path.write_text(json.dumps(credential_payload(existing_credentials, env), indent=2))
        import_credentials(credentials_path)

        imported_credentials = export_credentials()
        existing_workflows = export_workflows()
        workflow_path = temp / "workflow.json"
        workflow_path.write_text(
            json.dumps(
                workflow_payload(imported_credentials, existing_workflows, activate=args.activate),
                indent=2,
            )
        )
        import_workflow(workflow_path)

        imported_workflows = export_workflows()
        workflow_id = get_workflow_id(imported_workflows)
        if args.activate:
            set_workflow_active(workflow_id)
            restart_n8n()

    workflow_state = "active" if args.activate else "inactive"
    print(f"Imported workflow '{WORKFLOW_NAME}' ({workflow_state}).")
    print(f"Configured credentials: {DEEPSEEK_CREDENTIAL_NAME}, {POSTGRES_CREDENTIAL_NAME}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"setup_n8n failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
