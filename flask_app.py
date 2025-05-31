from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
import datetime
import os
import re
import pandas as pd
from jiraLogger import get_excel_entry

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this!

JIRA_DOMAIN = 'https://jira.critical.pt'

def get_pat():
    pat = session.get('JIRA_PAT')
    if not pat:
        pat = os.getenv('JIRA_PAT')
    return pat

def get_headers():
    pat = get_pat()
    return {
        'Authorization': f'Bearer {pat}' if pat else '',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }

@app.before_request
def require_pat():
    if request.endpoint not in ('set_pat', 'static'):
        pat = get_pat()
        if not pat:
            return redirect(url_for('set_pat'))

@app.route('/set_pat', methods=['GET', 'POST'])
def set_pat():
    if request.method == 'POST':
        pat = request.form.get('pat')
        if pat:
            session['JIRA_PAT'] = pat
            flash('JIRA PAT set successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Please enter a valid JIRA PAT.', 'danger')
    return render_template('set_pat.html')

def get_assigned_tasks():
    assigned_url = f'{JIRA_DOMAIN}/rest/api/2/search'
    jql = 'assignee = currentUser() ORDER BY updated DESC'
    params = {'jql': jql, 'maxResults': 100}
    response = requests.get(assigned_url, headers=get_headers(), params=params)
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
    response = requests.post(worklog_url, headers=get_headers(), json=worklog_payload)
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
    fetch_requested = (request.method == 'GET' and request.args.get('fetch') == '1')
    filter_requested = (request.method == 'POST' and filter_keyword) or (request.method == 'GET' and filter_keyword)

    if fetch_requested or filter_requested:
        # Fetch from JIRA and do NOT store in session
        tasks, error = get_assigned_tasks()
        if error:
            flash(error, 'danger')
            tasks = []
        if filter_keyword:
            tasks = [t for t in tasks if filter_keyword in t['fields']['summary'].lower()]
    else:
        # If not fetching/filtering, do not use session, just show empty or prompt user to fetch
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
    time_spent = ''
    date_input = ''
    dry_run = False
    # Fetch summary for the issue_key
    all_tasks, _ = get_assigned_tasks()
    summary = next((t['fields']['summary'] for t in all_tasks if t['key'] == issue_key), '')
    if request.method == 'POST':
        time_spent = request.form.get('time_spent', '')
        date_input = request.form.get('date_input', '')
        if 'dry_run' in request.form:
            # Just show dry run summary
            dry_run = True
            return render_template('log_time.html', issue_key=issue_key, summary=summary, time_spent=time_spent, date_input=date_input, dry_run=True)
        elif 'confirm' in request.form:
            # Actually log time
            try:
                if date_input:
                    started = datetime.datetime.strptime(date_input, "%H:%M %d-%m-%Y").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                else:
                    started = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            except ValueError:
                flash("Invalid date format. Use HH:MM DD-MM-YYYY.", 'danger')
                return render_template('log_time.html', issue_key=issue_key, summary=summary, time_spent=time_spent, date_input=date_input, dry_run=True)
            success, msg = log_work(issue_key, time_spent, started)
            flash(msg, 'success' if success else 'danger')
            # Do NOT clear or update session['tasks'] here, just redirect
            return redirect(url_for('index'))
    return render_template('log_time.html', issue_key=issue_key, summary=summary, time_spent=time_spent, date_input=date_input, dry_run=dry_run)

@app.route('/log_time_multiple', methods=['POST', 'GET'])
def log_time_multiple():
    if request.method == 'POST':
        selected_tasks = request.form.getlist('selected_tasks')
        if not selected_tasks:
            flash('No tasks selected.', 'danger')
            return redirect(url_for('index'))
        all_tasks, _ = get_assigned_tasks()
        key_to_summary = {t['key']: t['fields']['summary'] for t in all_tasks}
        selected_task_info = [(key, key_to_summary.get(key, '')) for key in selected_tasks]
        if 'confirm' in request.form:
            # Actually log work after dry run
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
            # Always show dry run before logging
            time_spent = request.form['time_spent']
            date_input = request.form['date_input']
            return render_template('log_time_multiple.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, time_spent=time_spent, date_input=date_input, dry_run=True)
        else:
            now = datetime.datetime.now().strftime('%H:%M %d-%m-%Y')
            return render_template('log_time_multiple.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, date_input=now)
    else:
        return redirect(url_for('index'))

@app.route('/log_time_multiple_individual', methods=['GET', 'POST'])
def log_time_multiple_individual():
    def is_valid_time_spent(val):
        # Accepts formats like 1h, 10m, 1h10m, 10h10m, etc. (at least one of h or m)
        return bool(re.fullmatch(r'([0-9]+h)?([0-9]+m)?', val.strip())) and val.strip() != ''

    def parse_time_spent(val):
        # Returns (hours, minutes) as integers
        match = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?', val.strip())
        if not match:
            return 0, 0
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours, minutes

    if request.method == 'POST':
        selected_tasks = request.form.getlist('selected_tasks')
        if not selected_tasks:
            flash('No tasks selected.', 'danger')
            return redirect(url_for('index'))
        all_tasks, _ = get_assigned_tasks()
        key_to_summary = {t['key']: t['fields']['summary'] for t in all_tasks}
        selected_task_info = [(key, key_to_summary.get(key, '')) for key in selected_tasks]
        if 'dry_run' in request.form:
            # Show dry run summary with status for each
            per_task_data = []
            for key in selected_tasks:
                time_spent = request.form.get(f'time_spent_{key}')
                date_input = request.form.get(f'date_input_{key}')
                status = 'ok'
                # Validate input
                if not time_spent or not is_valid_time_spent(time_spent):
                    status = 'Invalid time (use e.g. 1h10m, 10m, 2h)'
                try:
                    if date_input:
                        datetime.datetime.strptime(date_input, "%H:%M %d-%m-%Y")
                except Exception:
                    status = 'Invalid date'
                per_task_data.append({'key': key, 'summary': key_to_summary.get(key, ''), 'time_spent': time_spent, 'date_input': date_input, 'status': status})
            return render_template('log_time_multiple_individual.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info, per_task_data=per_task_data, dry_run=True)
        elif 'confirm' in request.form:
            # Actually log work for all tasks
            for key in selected_tasks:
                time_spent = request.form.get(f'time_spent_{key}')
                date_input = request.form.get(f'date_input_{key}')
                if not time_spent or not is_valid_time_spent(time_spent):
                    flash(f"Invalid time for {key}. Use e.g. 1h10m, 10m, 2h", 'danger')
                    return redirect(request.url)
                # If only hours, add 0m for display/logging clarity
                hours, minutes = parse_time_spent(time_spent)
                formatted_time_spent = ''
                if hours:
                    formatted_time_spent += f'{hours}h'
                if minutes or not hours:
                    formatted_time_spent += f'{minutes}m'
                try:
                    if date_input:
                        started = datetime.datetime.strptime(date_input, "%H:%M %d-%m-%Y").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                    else:
                        started = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                except ValueError:
                    flash(f"Invalid date format for {key}. Use HH:MM DD-MM-YYYY.", 'danger')
                    return redirect(request.url)
                success, msg = log_work(key, formatted_time_spent, started)
                flash(msg, 'success' if success else 'danger')
            return redirect(url_for('index'))
        else:
            return render_template('log_time_multiple_individual.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info)
    else:
        # GET: parse selected_tasks from query string
        selected_tasks = request.args.getlist('selected_tasks')
        if not selected_tasks:
            flash('No tasks selected.', 'danger')
            return redirect(url_for('index'))
        all_tasks, _ = get_assigned_tasks()
        key_to_summary = {t['key']: t['fields']['summary'] for t in all_tasks}
        selected_task_info = [(key, key_to_summary.get(key, '')) for key in selected_tasks]
        return render_template('log_time_multiple_individual.html', selected_tasks=selected_tasks, selected_task_info=selected_task_info)

@app.route('/excel_log', methods=['GET', 'POST'])
def excel_log():
    value1 = ''
    value2 = ''
    result = None
    if request.method == 'POST':
        value1 = request.form.get('value1', '')  # Name
        value2 = request.form.get('value2', '')  # Date
        if value1 and value2:
            cell = get_excel_entry(value2, value1, file_path='jira/BSP-G2_Daily_Tracker.xlsx')
            # Pass the cell as-is, do not replace newlines
            result = cell
    return render_template('excel_log.html', value1=value1, value2=value2, result=result)

if __name__ == '__main__':
    app.run(debug=True)
