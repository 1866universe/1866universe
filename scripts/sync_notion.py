import os
import sys
import re
import requests

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "3cf7e46a-d877-8038-bbad-eb12d53ad9a1")
GITHUB_ACTOR = os.getenv("GITHUB_ACTOR", "1866universe")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

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

DOMAIN_MAP = {
    "nlp": "Natural Language Processing",
    "translation": "Machine Translation",
    "linguistics": "Computational Linguistics",
    "vision": "Computer Vision",
    "audio": "Audio & Speech Processing",
    "infra": "Infrastructure & Tooling",
}


def clean_markdown_for_description(raw_md: str) -> str:
    """Clean markdown artifacts and extract the most meaningful summary text."""
    if not raw_md:
        return ""

    # Remove HTML comments and tags
    text = re.sub(r"<!--.*?-->", "", raw_md, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)

    # Remove code blocks and inline code
    text = re.sub(r"\x60\x60\x60[\s\S]*?\x60\x60\x60", "", text)
    text = re.sub(r"\x60[^\x60]*\x60", "", text)

    # Remove images: ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # Links -> keep visible label text only: [text](url) -> text
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)

    # Strip emphasis (bold, italic, strikethrough)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.*?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.*?)(?<!\s)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text, flags=re.DOTALL)

    lines = [line.strip() for line in text.split("\n")]
    filtered_lines = []

    for line in lines:
        if not line:
            if filtered_lines and filtered_lines[-1] != "":
                filtered_lines.append("")
            continue

        # Skip markdown headers and horizontal rules
        if line.startswith("#") or set(line) <= {"=", "-", "*", "_", "~", " "}:
            continue

        # Skip markdown table rows and table dividers
        if line.startswith("|") or (line.count("|") >= 2):
            continue

        # Strip blockquotes and bullet points
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)

        if not line:
            continue

        filtered_lines.append(line)

    cleaned_text = "\n".join(filtered_lines).strip()

    if cleaned_text:
        paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
        if paragraphs:
            summary = "\n\n".join(paragraphs[:3])
            return summary[:1900].strip()

    return cleaned_text[:1900].strip()


def fetch_readme_summary(repo_full_name: str, default_branch: str = "main") -> str:
    """Fetch README content from GitHub and return a clean summary."""
    readme_urls = [
        f"https://raw.githubusercontent.com/{repo_full_name}/{default_branch}/README.md",
        f"https://raw.githubusercontent.com/{repo_full_name}/master/README.md",
        f"https://raw.githubusercontent.com/{repo_full_name}/{default_branch}/readme.md",
    ]

    for url in readme_urls:
        try:
            res = requests.get(url, headers=GITHUB_HEADERS, timeout=10)
            if res.status_code == 200 and res.text.strip():
                summary = clean_markdown_for_description(res.text)
                if summary:
                    return summary
        except Exception as e:
            print(f"[Warning] Could not fetch README from {url}: {e}")

    return ""


def get_public_repos():
    url = f"https://api.github.com/users/{GITHUB_ACTOR}/repos?per_page=100&type=public"
    res = requests.get(url, headers=GITHUB_HEADERS)
    if res.status_code == 404 or (res.status_code == 200 and len(res.json()) == 0):
        url = f"https://api.github.com/orgs/{GITHUB_ACTOR}/repos?per_page=100&type=public"
        res = requests.get(url, headers=GITHUB_HEADERS)

    if res.status_code != 200:
        print(f"Error fetching repos: {res.status_code} - {res.text}")
        return []
    return res.json()


def get_existing_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    existing = {}
    has_more = True
    next_cursor = None

    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        res = requests.post(url, headers=NOTION_HEADERS, json=payload)
        if res.status_code != 200:
            print(f"Error querying Notion DB: {res.status_code} - {res.text}")
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


def infer_domain(name, description, topics):
    corpus = f"{name} {description or ''} {' '.join(topics)}".lower()
    for key, domain in DOMAIN_MAP.items():
        if key in corpus:
            return domain
    return "Universal & Multidisciplinary"


def sync_repo(repo, existing_pages):
    """Create or update one repository page in Notion."""
    name = repo.get("name")
    full_name = repo.get("full_name") or f"{GITHUB_ACTOR}/{name}"
    default_branch = repo.get("default_branch", "main")

    if not name:
        print("[Error] Repository has no name.")
        return False

    readme_summary = fetch_readme_summary(full_name, default_branch)

    if readme_summary:
        final_description = readme_summary
    else:
        final_description = repo.get("description") or "No description provided."

    github_url = repo.get("html_url")
    updated_at = repo.get("updated_at")
    topics = repo.get("topics", [])
    domain = infer_domain(name, final_description, topics)

    is_archived = repo.get("archived", False)
    status_value = "Done" if is_archived else "In progress"

    properties = {
        "Name": {
            "title": [
                {
                    "text": {
                        "content": name[:2000],
                    }
                }
            ]
        },
        "Description": {
            "rich_text": [
                {
                    "text": {
                        "content": final_description[:2000],
                    }
                }
            ]
        },
        "Domain": {
            "select": {
                "name": domain,
            }
        },
        "Status": {
            "status": {
                "name": status_value,
            }
        },
        "GitHub URL": {
            "url": github_url,
        },
        "Updated": {
            "date": {
                "start": updated_at,
            }
        },
    }

    if name in existing_pages:
        action = "Updated"
        page_id = existing_pages[name]
        url = f"https://api.notion.com/v1/pages/{page_id}"

        response = requests.patch(
            url,
            headers=NOTION_HEADERS,
            json={"properties": properties},
        )
    else:
        action = "Created"
        url = "https://api.notion.com/v1/pages"

        payload = {
            "parent": {
                "database_id": DATABASE_ID,
            },
            "properties": properties,
        }

        response = requests.post(
            url,
            headers=NOTION_HEADERS,
            json=payload,
        )

    if response.status_code in (200, 201):
        print(f"[{action}] {name} -> Notion successfully.")
        return True

    print(
        f"[Error {response.status_code}] "
        f"Failed to {action.lower()} {name}: {response.text}"
    )
    return False


def main():
    if not NOTION_TOKEN:
        print("Error: NOTION_TOKEN is missing!")
        sys.exit(1)

    print(f"Fetching repositories for target: {GITHUB_ACTOR}...")
    repos = get_public_repos()
    print(f"Found {len(repos)} repositories.")

    if not repos:
        print("No repositories found to sync.")
        return

    print("Querying existing pages in Notion...")
    existing_pages = get_existing_notion_pages()
    print(f"Found {len(existing_pages)} existing pages in Notion.")

    failed_repos = []
    for repo in repos:
        success = sync_repo(repo, existing_pages)
        if not success:
            failed_repos.append(repo.get("name"))

    if failed_repos:
        print(f"\n[Failure] Sync failed for {len(failed_repos)} repositories: {', '.join(failed_repos)}")
        sys.exit(1)

    print("\nSync completed successfully for all repositories.")


if __name__ == "__main__":
    main()
