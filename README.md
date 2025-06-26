# Jira Confluence Automator

This script automates the process of converting tasks in Confluence pages into Jira issues.

## Features

- Scans a Confluence page and its children for incomplete tasks.
- Creates a Jira issue for each incomplete task.
- Links the created Jira issue back to the Confluence page.
- Replaces the Confluence task with a Jira issue macro.
- Logs all operations for easy tracking and debugging.
- Provides an undo script to revert all changes.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/jira-confluence-automator.git](https://github.com/your-username/jira-confluence-automator.git)
    cd jira-confluence-automator
    ```

2.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the application:**
    Open the `config.py` file and update the following variables with your Jira and Confluence details:
    - `JIRA_URL`: Your Jira instance URL.
    - `CONFLUENCE_URL`: Your Confluence instance URL.
    - `JIRA_API_TOKEN`: Your Jira personal access token.
    - `CONFLUENCE_API_TOKEN`: Your Confluence personal access token.
    - `JIRA_PROJECT_KEY`: The key of the Jira project where you want to create the issues.
    - `WORK_PACKAGE_ISSUE_TYPE_ID`: The ID of the "Work Package" issue type in your Jira project.
    - `TASK_ISSUE_TYPE_ID`: The ID of the "Task" issue type in your Jira project.
    - `JIRA_PARENT_WP_CUSTOM_FIELD_ID`: The ID of the custom field used to link a task to its parent work package.

## Usage

1.  **Create an `input.xlsx` file:**
    In the root of the project, create a file named `input.xlsx` with a single column: `ConfluencePageURL`. Add the URLs of the Confluence pages you want to process.

2.  **Run the script:**
    ```bash
    python main.py
    ```

3.  **Check the output:**
    The script will create an `output` folder with a new Excel file containing the results of the automation. It will also create a `logs` folder with a log file for the current run.

## Undo Script

If you need to revert the changes made by the script, you can run the `undo_automation.py` script:

```bash
python undo_automation.py