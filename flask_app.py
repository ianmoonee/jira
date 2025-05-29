from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this!

JIRA_DOMAIN = 'https://jira.critical.pt'
PAT = os.getenv('JIRA_PAT')

HEADERS = {
    'Authorization': f'Bearer {PAT}',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}

def get_assigned_tasks():
    assigned_url = f'{JIRA_DOMAIN}/rest/api/2/search'
    jql = 'assignee = currentUser() ORDER BY updated DESC'
    params = {'jql': jql, 'maxResults': 100}
    response = requests.get(assigned_url, headers=HEADERS, params=params)
    if response.status_code != 200:
        return [], f"Failed to fetch tasks: {response.status_code} {response.text}"
    issues = response.json().get('issues', [])
    return issues, None

def log_work(issue_key, time_spent, started):
    worklog_url = f'{JIRA_DOMAIN}/rest/api/2/issue/{issue_key}/worklog'
    worklog_payload = {
        "started": started,
        "timeSpent": time_spent
    }
    response = requests.post(worklog_url, headers=HEADERS, json=worklog_payload)
    if response.status_code == 201:
        return True, f"Successfully logged {time_spent} on {issue_key}"
    else:
        return False, f"Failed to log work: {response.status_code} {response.text}"

@app.route('/', methods=['GET', 'POST'])
def index():
    # Default sort by summary, descending
    sort_by = request.args.get('sort_by', 'summary')
    sort_order = request.args.get('sort_order', 'desc')
    filter_keyword = request.form.get('filter', '').lower() if request.method == 'POST' else request.args.get('filter', '').lower()
    tasks = []
    error = None
    if (request.method == 'POST' and filter_keyword) or (request.method == 'GET' and filter_keyword):
        # If filtering, fetch tasks and filter
        tasks, error = get_assigned_tasks()
        if error:
            flash(error, 'danger')
            tasks = []
        if filter_keyword:
            tasks = [t for t in tasks if filter_keyword in t['fields']['summary'].lower()]
    elif request.method == 'GET' and request.args.get('fetch') == '1':
        # Only fetch tasks if fetch=1 in query string
        tasks, error = get_assigned_tasks()
        if error:
            flash(error, 'danger')
            tasks = []
    # Sorting
    if tasks:
        reverse = (sort_order == 'desc')
        if sort_by == 'summary':
            tasks = sorted(tasks, key=lambda t: t['fields']['summary'].lower(), reverse=reverse)
        else:
            tasks = sorted(tasks, key=lambda t: t['key'], reverse=reverse)
    return render_template('index.html', tasks=tasks, filter_keyword=filter_keyword, sort_by=sort_by, sort_order=sort_order)

@app.route('/log_time/<issue_key>', methods=['GET', 'POST'])
def log_time(issue_key):
    if request.method == 'POST':
        time_spent = request.form['time_spent']
        date_input = request.form['date_input']
        try:
            if date_input:
                started = datetime.datetime.strptime(date_input, "%Y-%m-%d %H:%M").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            else:
                started = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+0000')
        except ValueError:
            flash("Invalid date format. Use YYYY-MM-DD HH:MM.", 'danger')
            return redirect(request.url)
        success, msg = log_work(issue_key, time_spent, started)
        flash(msg, 'success' if success else 'danger')
        return redirect(url_for('index'))
    return render_template('log_time.html', issue_key=issue_key)

@app.route('/upload_file', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash("No file selected.", 'danger')
            return redirect(request.url)
        lines = file.read().decode('utf-8').splitlines()
        tasks, _ = get_assigned_tasks()
        summary_to_key = {t['fields']['summary']: t['key'] for t in tasks}
        dry_run_results = []
        for line in lines:
            parts = line.strip().split(',')
            if len(parts) != 3:
                flash(f"Invalid line format: {line.strip()}", 'danger')
                continue
            task_name, time_spent, date_input = parts
            issue_key = summary_to_key.get(task_name)
            if not issue_key:
                flash(f"Task not found: {task_name}", 'danger')
                continue
            try:
                started = datetime.datetime.strptime(date_input, "%Y-%m-%d %H:%M").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            except ValueError:
                flash(f"Invalid date format for task {task_name}. Use YYYY-MM-DD HH:MM.", 'danger')
                continue
            dry_run_results.append((issue_key, time_spent, started))
        if not dry_run_results:
            flash("No valid tasks to process.", 'info')
            return redirect(request.url)
        # Actually log work
        for issue_key, time_spent, started in dry_run_results:
            success, msg = log_work(issue_key, time_spent, started)
            flash(msg, 'success' if success else 'danger')
        return redirect(url_for('index'))
    return render_template('upload_file.html')

@app.route('/log_time_multiple', methods=['POST', 'GET'])
def log_time_multiple():
    if request.method == 'POST':
        selected_tasks = request.form.getlist('selected_tasks')
        if not selected_tasks:
            flash('No tasks selected.', 'danger')
            return redirect(url_for('index'))
        # Get all tasks to map key to summary
        all_tasks, _ = get_assigned_tasks()
        key_to_summary = {t['key']: t['fields']['summary'] for t in all_tasks}
        selected_task_info = [(key, key_to_summary.get(key, '')) for key in selected_tasks]
        if 'confirm' in request.form:
            time_spent = request.form['time_spent']
            date_input = request.form['date_input']
            try:
                if date_input:
                    started = datetime.datetime.strptime(date_input, "%H:%M %d-%m-%Y").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                else:
                    started = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            except ValueError:
                flash("Invalid date format. Use HH:MM DD-MM-YYYY.", 'danger')
                return render_template('log_time_multiple.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, time_spent=time_spent, date_input=date_input, dry_run=True)
            for issue_key in selected_tasks:
                success, msg = log_work(issue_key, time_spent, started)
                flash(msg, 'success' if success else 'danger')
            return redirect(url_for('index'))
        elif 'time_spent' in request.form:
            time_spent = request.form['time_spent']
            date_input = request.form['date_input']
            return render_template('log_time_multiple.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, time_spent=time_spent, date_input=date_input, dry_run=True)
        else:
            # Pre-fill date input with current date/time in HH:MM DD-MM-YYYY
            now = datetime.datetime.now().strftime('%H:%M %d-%m-%Y')
            return render_template('log_time_multiple.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, date_input=now)
    else:
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
