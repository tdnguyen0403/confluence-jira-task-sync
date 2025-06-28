# Jira Confluence Automator

The Jira Confluence Automator is a Python script designed to streamline task management by automatically converting incomplete Confluence tasks into Jira issues. This tool enhances efficiency by integrating Confluence-based task tracking with Jira's robust issue management capabilities.

## ✨ Features

* **Task Scanning**: Identifies incomplete tasks within specified Confluence pages and their child pages.
* **Jira Issue Creation**: Automatically creates a Jira issue for each identified incomplete task.
* **Bi-directional Linking**: Establishes a link from the newly created Jira issue back to its originating Confluence page.
* **Confluence Integration**: Replaces the original Confluence task with a Jira issue macro, providing a direct link to the Jira issue within Confluence.
* **Comprehensive Logging**: Generates detailed logs for all operations, facilitating easy tracking, debugging, and auditing.
* **Undo Capability**: Includes a dedicated script to revert all changes made during the automation process.
* **Secure Configuration**: Utilizes environment variables for sensitive credentials and a JSON file for general configuration.

## 🚀 Setup

To get started with the Jira Confluence Automator, follow these steps:

1.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd jira_confluence_automator
    ```
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment Variables**:
    * Create a `.env` file in the project's root directory.
    * Refer to `.env.example` for the required format and add your sensitive credentials.
    * Generate the environment variable setup script:
        ```bash
        python generate_env.py
        ```
    * Execute the generated script in your terminal to set the variables:
        ```bash
        set_env.bat  # On Windows
        # Or for Linux/macOS, use:
        # source set_env.sh
        ```
4.  **Define User Inputs**:
    * Open `user_input.json`.
    * Add the URLs of the Confluence pages you wish to process to the `ConfluencePageURLs` list.

## 💡 Usage

Once configured, run the automation script:

```bash
python main.py