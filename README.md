# Google Drive Monitor to MongoDB

This Python application monitors a specified Google Drive folder for new files. When a new file is detected, its metadata (including filename, ID, creation date, MIME type, and a web link) is uploaded to a MongoDB database.

## Prerequisites

1.  **Python 3.7+**
2.  **MongoDB Instance:**
    *   A running MongoDB instance (local or cloud-hosted like MongoDB Atlas).
    *   You'll need the MongoDB connection URI.
3.  **Google Cloud Platform Project:**
    *   A Google Cloud Platform (GCP) project with the Google Drive API enabled.
    *   OAuth 2.0 credentials for a desktop application.

## Setup Instructions

### 1. Clone the Repository (or create the files)

If this project were in a Git repository, you'd clone it. For now, ensure all project files are in a directory named `google_drive_monitor`.

### 2. Install Dependencies

Navigate to the `google_drive_monitor` directory in your terminal and install the required Python packages:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Google Drive API Access

a.  **Enable Google Drive API:**
    *   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Select your project or create a new one.
    *   Go to "APIs & Services" > "Library".
    *   Search for "Google Drive API" and enable it.

b.  **Create OAuth 2.0 Credentials:**
    *   Go to "APIs & Services" > "Credentials".
    *   Click "+ CREATE CREDENTIALS" > "OAuth client ID".
    *   If prompted, configure the OAuth consent screen:
        *   Choose "External" (unless you have a G Suite organization).
        *   Fill in the app name (e.g., "Drive Monitor App"), user support email, and developer contact information.
        *   For Scopes, you can leave it blank for now or add `https://www.googleapis.com/auth/drive.metadata.readonly` and `https://www.googleapis.com/auth/drive.readonly`. The script will request necessary scopes.
        *   Add your email address as a Test User if your app is in "Testing" mode.
    *   For "Application type", select "Desktop app".
    *   Give it a name (e.g., "Drive Monitor Desktop Client").
    *   Click "CREATE".
    *   A dialog will appear with your "Client ID" and "Client secret". Click "DOWNLOAD JSON".
    *   Rename the downloaded JSON file to `credentials.json` and place it in the `google_drive_monitor` project directory. **IMPORTANT: Do NOT commit `credentials.json` to public version control if this were a public repository.**

### 4. Configure Environment Variables

Create a file named `.env` in the `google_drive_monitor` directory with the following content:

```env
# MongoDB Configuration
MONGO_URI="your_mongodb_connection_string"
MONGO_DATABASE_NAME="google_drive_files"
MONGO_COLLECTION_NAME="file_metadata"

# Google Drive Configuration
DRIVE_FOLDER_ID="your_google_drive_folder_id_to_monitor" # ID of the specific folder
# To find the Folder ID: Open the folder in Google Drive. The ID is the last part of the URL.
# e.g., if URL is https://drive.google.com/drive/folders/123AbcXYZ789, then ID is 123AbcXYZ789

# Optional: Path to your Google API credentials JSON file (if not named 'credentials.json' or not in the root)
# GOOGLE_CREDENTIALS_PATH="path/to/your/credentials.json"

# Optional: Path for storing the token.json (stores user's access and refresh tokens)
# TOKEN_JSON_PATH="token.json"
```

*   Replace `your_mongodb_connection_string` with your actual MongoDB connection URI (e.g., `mongodb://localhost:27017/` or a MongoDB Atlas URI).
*   Replace `your_google_drive_folder_id_to_monitor` with the ID of the Google Drive folder you want to monitor.
*   Adjust `MONGO_DATABASE_NAME` and `MONGO_COLLECTION_NAME` if desired.

### 5. First Run (Authentication)

The first time you run `main.py`, it will attempt to authenticate with Google Drive.
*   A URL will be printed in the console.
*   Copy this URL and open it in a web browser.
*   Choose your Google account and grant the requested permissions.
*   After successful authorization, you'll be redirected (this might show an error page if no local server is running, which is fine for desktop apps). The script will automatically receive the authorization code or detect the `token.json` file.
*   A `token.json` file will be created in your project directory (or the path specified by `TOKEN_JSON_PATH`). This file stores your access and refresh tokens, so you don't have to re-authenticate every time. **IMPORTANT: Do NOT commit `token.json` to public version control.**

## Running the Application

Once setup is complete, activate your virtual environment and run the main script:

```bash
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
python main.py
```

The script will:
1.  Connect to MongoDB.
2.  Authenticate with Google Drive (using `token.json` if it exists, or prompting for new authentication).
3.  Periodically check the specified Google Drive folder for new files that haven't been logged in MongoDB.
4.  For each new file, it will store its metadata (ID, name, MIME type, creation time, web link) in the MongoDB collection.

## How it Works (Briefly)

*   **`main.py`**: Orchestrates the process. Sets up a loop to periodically check for new files.
*   **`google_drive_utils.py`**: Handles all interactions with the Google Drive API (authentication, listing files, getting file metadata).
*   **`mongo_utils.py`**: Handles all interactions with MongoDB (connecting, checking if a file exists, inserting file metadata).
*   The script keeps track of processed files by storing their Google Drive File IDs in MongoDB to avoid reprocessing.

## Important Notes

*   **Error Handling**: This is a basic implementation. Robust error handling (e.g., for network issues, API errors, DB errors) would be needed for a production system.
*   **Rate Limiting**: Be mindful of Google Drive API rate limits if you plan to check very frequently or monitor a very large number of files.
*   **Security**:
    *   Keep your `credentials.json` and `token.json` files secure and do not expose them.
    *   Use environment variables for sensitive information like your MongoDB URI.