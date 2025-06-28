# Jira Confluence Automator

This script automates the process of converting tasks in Confluence pages into Jira issues.

## Features

- Scans a Confluence page and its children for incomplete tasks.
- Creates a Jira issue for each incomplete task.
- Links the created Jira issue back to the Confluence page.
- Replaces the Confluence task with a Jira issue macro.
- Logs all operations for easy tracking and debugging.
- Provides an undo script to revert all changes.
- Uses environment variables for secrets and a JSON file for configuration.

## Setup

1.  **Clone the repository.**
2.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Create a `.env` file:**
    Create this file in the root of the project and add your sensitive credentials. See `.env.example` for the required format.
4.  **Configure User Inputs:**
    Open the `user_input.json` file and add the Confluence Page URLs you want to process to the `ConfluencePageURLs` list.
5.  **Set Environment Variables:**
    Run the following command to generate a script that sets your environment variables:
    ```bash
    python generate_env.py
    ```
    Then, run the generated script in your terminal:
    ```bash
    set_env.bat
    ```

## Usage

1.  **Run the script:**
    ```bash
    python main.py
    ```
2.  **Check the output:**
    The script will create an `output` folder with a new Excel file containing the results of the automation. It will also create a `logs` folder with a log file for the current run.

## Undo Script

If you need to revert the changes made by the script, you can run the `undo_automation.py` script:

```bash
python undo_automation.py