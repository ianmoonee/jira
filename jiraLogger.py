import sys
import requests
import datetime
import os
import time
from tkinter import Tk, Label, Listbox, Button, Entry, filedialog, messagebox, Scrollbar, END, MULTIPLE, Frame
from tkinter import ttk  # Import ttk for themed widgets

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
        messagebox.showerror("Error", f"Failed to fetch tasks: {response.status_code} {response.text}")
        return []

    issues = response.json().get('issues', [])
    if not issues:
        messagebox.showinfo("No Tasks", "No tasks assigned to you.")
        return []

    return issues

def log_work(issue_key, time_spent, started):
    worklog_url = f'{JIRA_DOMAIN}/rest/api/2/issue/{issue_key}/worklog'
    worklog_payload = {
        "started": started,
        "timeSpent": time_spent
    }

    response = requests.post(worklog_url, headers=HEADERS, json=worklog_payload)
    if response.status_code == 201:
        messagebox.showinfo("Success", f"Successfully logged {time_spent} on {issue_key}")
    else:
        messagebox.showerror("Error", f"Failed to log work: {response.status_code} {response.text}")

# === MAIN WINDOW ===
class JiraLoggerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JIRA Task Logger")
        self.root.geometry("800x600")

        # Set the theme
        style = ttk.Style()
        style.theme_use("clam")

        # Configure grid weights for responsiveness
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # Task List Section
        self.task_list_label = ttk.Label(root, text="Assigned Tasks", font=("Arial", 14, "bold"))
        self.task_list_label.grid(row=0, column=0, columnspan=3, pady=10, sticky="ew")

        # Frame for Listbox and Scrollbar
        list_frame = Frame(root)
        list_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.task_list = Listbox(list_frame, selectmode=MULTIPLE, width=80, height=20)
        self.task_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.task_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.task_list.config(yscrollcommand=scrollbar.set)

        # Buttons and Search Section
        button_frame = Frame(root)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)
        button_frame.columnconfigure(3, weight=2)  # Search bar gets more space
        button_frame.columnconfigure(4, weight=1)

        self.fetch_tasks_button = ttk.Button(button_frame, text="Fetch Tasks", command=self.fetch_tasks)
        self.fetch_tasks_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.log_time_button = ttk.Button(button_frame, text="Log Time", command=self.log_time)
        self.log_time_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.upload_file_button = ttk.Button(button_frame, text="Upload Task File", command=self.log_from_file)
        self.upload_file_button.grid(row=0, column=2, padx=5, sticky="ew")

        self.search_bar = Entry(button_frame, fg="grey")  # Use the standard Entry widget
        self.search_bar.grid(row=0, column=3, padx=5, sticky="ew")
        self.search_bar.insert(0, "Search tasks...")
        self.search_bar.bind("<FocusIn>", self._clear_placeholder)
        self.search_bar.bind("<FocusOut>", self._add_placeholder)

        self.search_button = ttk.Button(button_frame, text="Filter", command=self.apply_filter)
        self.search_button.grid(row=0, column=4, padx=5, sticky="ew")

        self.assigned_tasks = []

    def _clear_placeholder(self, event):
        if self.search_bar.get() == "Search tasks...":
            self.search_bar.delete(0, END)
            self.search_bar.config(fg="black")

    def _add_placeholder(self, event):
        if not self.search_bar.get():
            self.search_bar.insert(0, "Search tasks...")
            self.search_bar.config(fg="grey")

    def fetch_tasks(self):
        tasks = get_assigned_tasks()
        if tasks:
            self.task_list.delete(0, END)
            self.assigned_tasks = tasks
            for task in tasks:
                self.task_list.insert(END, f"{task['key']} - {task['fields']['summary']}")

    def apply_filter(self):
        filter_keyword = self.search_bar.get().strip().lower()
        if not filter_keyword:
            self.fetch_tasks()
            return

        filtered_tasks = [
            task for task in self.assigned_tasks
            if filter_keyword in task['fields']['summary'].lower()
        ]
        self.task_list.delete(0, END)
        for task in filtered_tasks:
            self.task_list.insert(END, f"{task['key']} - {task['fields']['summary']}")

    def log_time(self):
        selected_items = self.task_list.curselection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more tasks to log time.")
            return

        time_spent = self.simple_input_dialog("Time Spent", "Enter time spent (e.g., 1h, 30m):")
        if not time_spent:
            return

        date_input = self.simple_input_dialog("Start Date", "Enter start date and time (YYYY-MM-DD HH:MM), or leave blank for now:")
        try:
            current_start_time = datetime.datetime.strptime(date_input, "%Y-%m-%d %H:%M") if date_input else datetime.datetime.now()
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD HH:MM.")
            return

        for index in selected_items:
            task_key = self.task_list.get(index).split(" - ")[0]
            started = current_start_time.strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            log_work(task_key, time_spent, started)

    def log_from_file(self):
        file_path = filedialog.askopenfilename(title="Select Task File", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if not file_path:
            return

        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()

            dry_run_results = []
            for line in lines:
                parts = line.strip().split(',')
                if len(parts) != 3:
                    messagebox.showerror("Error", f"Invalid line format: {line.strip()}")
                    continue

                task_name, time_spent, date_input = parts
                matching_task = next((task for task in self.assigned_tasks if task['fields']['summary'] == task_name), None)
                if not matching_task:
                    messagebox.showerror("Error", f"Task not found: {task_name}")
                    continue

                issue_key = matching_task['key']
                try:
                    started = datetime.datetime.strptime(date_input, "%Y-%m-%d %H:%M").strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                except ValueError:
                    messagebox.showerror("Error", f"Invalid date format for task {task_name}. Use YYYY-MM-DD HH:MM.")
                    continue

                dry_run_results.append((issue_key, time_spent, started))

            if not dry_run_results:
                messagebox.showinfo("Dry Run", "No valid tasks to process.")
                return

            dry_run_message = "The following tasks will be logged:\n\n"
            for issue_key, time_spent, started in dry_run_results:
                dry_run_message += f"- {issue_key}: {time_spent} at {started}\n"

            proceed = messagebox.askyesno("Dry Run", f"{dry_run_message}\nDo you want to proceed?")
            if not proceed:
                messagebox.showinfo("Cancelled", "No tasks were logged.")
                return

            for issue_key, time_spent, started in dry_run_results:
                log_work(issue_key, time_spent, started)
                time.sleep(1)

            messagebox.showinfo("Success", "All tasks from the file have been logged.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process the file: {str(e)}")

    def simple_input_dialog(self, title, prompt):
        input_dialog = Tk()
        input_dialog.withdraw()
        return input_dialog.simpledialog.askstring(title, prompt)

# === MAIN ===
if __name__ == "__main__":
    root = Tk()
    app = JiraLoggerApp(root)
    root.mainloop()