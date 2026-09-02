import os
import sys
import requests

# Environment Variables
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "3cf7e46a-d877-8038-bbad-eb12d53ad9a1")
GITHUB_ACTOR = os.getenv("GITHUB_ACTOR", "1866universe")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Repositories to ignore during sync
IGNORED_REPOS = {"1866universe", ".github"}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"


def get_public_repos():
    """Fetch all public repositories for the user or organization."""
    url = f"https://api.github.com/users/{GITHUB_ACTOR}/repos?per_page=100&type=public"
    res = requests.get(url, headers=GITHUB_HEADERS, timeout=15)
    
    if res.status_code == 404 or (res.status_code == 200 and len(res.json()) == 0):
        url = f"https://api.github.com/orgs/{GITHUB_ACTOR}/repos?per_page=100&type=public"
        res = requests.get(url, headers=GITHUB_HEADERS, timeout=15)

    if res.status_code != 200:
        print(f"[Error] Fetching repos failed: {res.status_code} - {res.text}")
        return []
    return res.json()


def get_existing_notion_pages():
    """Retrieve existing pages from Notion database to prevent duplicates."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    existing = {}
    has_more = True
    next_cursor = None

    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        res = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        if res.status_code != 200:
            print(f"[Error] Querying Notion DB failed: {res.status_code} - {res.text}")
            sys.exit(1)

        data = res.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            name_prop = props.get("Name", {}).get("title", [])
            if name_prop:
                repo_name = name_prop[0].get("text", {}).get("content")
                existing[repo_name] = page["id"]

        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    return existing


def sync_repo(repo, existing_pages):
    """Create a new page or safely update structural properties in Notion."""
    name = repo.get("name")
    if not name:
        return False

    # Skip ignored repositories
    if name in IGNORED_REPOS:
        print(f"[Skipped] {name} is in the ignored list.")
        return True

    github_url = repo.get("html_url")
    updated_at = repo.get("updated_at")
    raw_description = repo.get("description") or ""
    is_archived = repo.get("archived", False)
    status_value = "Done" if is_archived else "In progress"

    # Properties updated for both new and existing pages
    properties = {
        "Name": {
            "title": [{"text": {"content": name[:100]}}]
        },
        "Status": {
            "status": {"name": status_value}
        },
        "GitHub URL": {
            "url": github_url
        },
        "Updated": {
            "date": {"start": updated_at}
        },
    }

    if name in existing_pages:
        # Safe Update: Only refresh technical meta without wiping custom descriptions
        action = "Updated"
        page_id = existing_pages[name]
        url = f"https://api.notion.com/v1/pages/{page_id}"

        response = requests.patch(
            url,
            headers=NOTION_HEADERS,
            json={"properties": properties},
            timeout=15,
        )
    else:
        # Create: Set default structure + initial GitHub short description
        action = "Created"
        url = "https://api.notion.com/v1/pages"

        if raw_description:
            properties["Description"] = {
                "rich_text": [{"text": {"content": raw_description[:1000]}}]
            }

        properties["Domain"] = {
            "select": {"name": "Universal & Multidisciplinary"}
        }

        payload = {
            "parent": {"database_id": DATABASE_ID},
            "properties": properties,
        }

        response = requests.post(
            url,
            headers=NOTION_HEADERS,
            json=payload,
            timeout=15,
        )

    if response.status_code in (200, 201):
        print(f"[{action}] {name} synced successfully.")
        return True

    print(f"[Error {response.status_code}] Failed to {action.lower()} {name}: {response.text}")
    return False


def main():
    if not NOTION_TOKEN:
        print("[Error] NOTION_TOKEN environment variable is missing!")
        sys.exit(1)

    print(f"Fetching public repositories for: {GITHUB_ACTOR}...")
    repos = get_public_repos()
    print(f"Found {len(repos)} repositories.")

    if not repos:
        print("No repositories to sync.")
        return

    print("Querying Notion database...")
    existing_pages = get_existing_notion_pages()
    print(f"Found {len(existing_pages)} existing pages.")

    failed_repos = []
    for repo in repos:
        success = sync_repo(repo, existing_pages)
        if not success:
            failed_repos.append(repo.get("name"))

    if failed_repos:
        print(f"\n[Warning] Sync encountered issues on: {', '.join(failed_repos)}")
        sys.exit(1)

    print("\nAll repositories successfully synced to Notion.")


if __name__ == "__main__":
    main()
