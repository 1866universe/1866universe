import os
import requests

GITHUB_USERNAME = "1866universe"
API_URL = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?sort=updated&per_page=100"

def get_public_repos():
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
        
    response = requests.get(API_URL, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching repos: {response.status_code}")
        return []
    
    repos = response.json()
    # فیلتر کردن مخزن پروفایل (1866universe) و فورک‌ها
    showcase_repos = [
        repo for repo in repos 
        if repo["name"].lower() != GITHUB_USERNAME.lower() and not repo["fork"]
    ]
    return showcase_repos

def generate_markdown_table(repos):
    if not repos:
        return "No public repositories available yet."
    
    header = "| Repository | Description / Focus | Primary Domain |\n| :--- | :--- | :--- |\n"
    rows = []
    for r in repos:
        name = r["name"]
        url = r["html_url"]
        desc = r["description"] or "Core research & infrastructure"
        topics = r.get("topics", [])
        domain = topics[0].title() if topics else (r["language"] or "Multidisciplinary")
        
        rows.append(f"| [{name}]({url}) | {desc} | {domain} |")
        
    return header + "\n".join(rows)

def update_readme():
    readme_path = "README.md"
    if not os.path.exists(readme_path):
        print("README.md not found!")
        return

    repos = get_public_repos()
    new_table = generate_markdown_table(repos)

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = "<!-- REPO-LIST:START -->"
    end_tag = "<!-- REPO-LIST:END -->"

    if start_tag in content and end_tag in content:
        before = content.split(start_tag)[0]
        after = content.split(end_tag)[1]
        updated_content = f"{before}{start_tag}\n\n{new_table}\n\n{end_tag}{after}"
        
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print("README.md successfully updated with dynamic repository list.")
    else:
        print("Marker tags <!-- REPO-LIST:START --> and <!-- REPO-LIST:END --> not found.")

if __name__ == "__main__":
    update_readme()
