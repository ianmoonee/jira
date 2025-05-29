import requests
import datetime
import os
import time

# === CONFIG ===
JIRA_DOMAIN = 'https://jira.critical.pt'
PAT = os.getenv('JIRA_PAT')  # Ensure you export JIRA_PAT in your bashrc

HEADERS = {
    'Authorization': f'Bearer {PAT}',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}

# === FUNCTIONS ===
def get_assigned_tasks():
    assigned_url = f'{JIRA_DOMAIN}/rest/api/2/search'
    jql = 'assignee = currentUser() ORDER BY updated DESC'
    params = {'jql': jql, 'maxResults': 100}

    response = requests.get(assigned_url, headers=HEADERS, params=params)
    if response.status_code != 200:
        return []

    issues = response.json().get('issues', [])
    return issues

def log_work(issue_key, time_spent, started):
    worklog_url = f'{JIRA_DOMAIN}/rest/api/2/issue/{issue_key}/worklog'
    worklog_payload = {
        "started": started,
        "timeSpent": time_spent
    }

    response = requests.post(worklog_url, headers=HEADERS, json=worklog_payload)
    return response.status_code == 201