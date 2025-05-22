import os
import logging
from typing import Union, Optional # Import Union and Optional for older Python compatibility
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Define the scopes required by the application
# drive.readonly allows reading file content and metadata.
# If you needed to modify files, you'd use 'https://www.googleapis.com/auth/drive'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Get credential and token paths from environment variables or use defaults
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
TOKEN_JSON_PATH = os.getenv('TOKEN_JSON_PATH', 'token.json')
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

def get_drive_service():
    """
    Authenticates with Google Drive API and returns a service object.
    Handles token refresh and new user authorization.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_JSON_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_JSON_PATH, SCOPES)
            logging.info("Loaded credentials from token.json.")
        except Exception as e:
            logging.error(f"Error loading credentials from {TOKEN_JSON_PATH}: {e}. Will attempt re-authentication.")
            creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logging.info("Credentials expired, attempting to refresh...")
                creds.refresh(Request())
                logging.info("Credentials refreshed successfully.")
            except Exception as e:
                logging.error(f"Failed to refresh token: {e}. Need to re-authenticate.")
                creds = None # Force re-authentication
        else:
            logging.info("No valid credentials found, initiating new authorization flow.")
            if not os.path.exists(CREDENTIALS_PATH):
                logging.error(f"Credentials file '{CREDENTIALS_PATH}' not found. "
                              "Please download it from Google Cloud Console and place it in the project directory.")
                raise FileNotFoundError(f"'{CREDENTIALS_PATH}' not found. Cannot authenticate.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                # Use a specific port or let it choose one automatically.
                # For desktop apps, running a local server is common.
                # Let's try a fixed port, e.g., 8080. Ensure this port is not in use by another app.
                # You will then need to add http://localhost:8080/ and http://127.0.0.1:8080/
                # to your Authorized redirect URIs in Google Cloud Console.
                fixed_port = 8080
                logging.info(f"Attempting to run local server on port {fixed_port} for authentication.")
                creds = flow.run_local_server(port=fixed_port)
                logging.info(f"Authorization flow completed using port {fixed_port}. Credentials obtained.")
            except OSError as e:
                if "Address already in use" in str(e):
                    logging.error(f"Port {fixed_port} is already in use. Please choose a different port or close the application using it.")
                    logging.error("You can try changing 'fixed_port' in google_drive_utils.py to another value (e.g., 8888, 9000).")
                    raise ConnectionError(f"Port {fixed_port} already in use.") from e
                else:
                    logging.error(f"An OS error occurred during authorization flow: {e}")
                    raise ConnectionError(f"Failed to complete Google authentication due to OS error: {e}") from e
            except Exception as e:
                logging.error(f"Error during authorization flow: {e}")
                raise ConnectionError(f"Failed to complete Google authentication: {e}") from e

        # Save the credentials for the next run
        try:
            with open(TOKEN_JSON_PATH, 'w') as token_file:
                token_file.write(creds.to_json())
            logging.info(f"Credentials saved to {TOKEN_JSON_PATH}.")
        except Exception as e:
            logging.error(f"Error saving token to {TOKEN_JSON_PATH}: {e}")

    if not creds:
        logging.error("Failed to obtain Google Drive credentials.")
        return None

    try:
        service = build('drive', 'v3', credentials=creds)
        logging.info("Google Drive API service built successfully.")
        return service
    except Exception as e:
        logging.error(f"Failed to build Google Drive service: {e}")
        return None

def list_new_files_in_folder(service, folder_id: str, processed_file_ids: set) -> list:
    """
    Lists files in a specific Google Drive folder that are not in processed_file_ids.
    Returns a list of file metadata dictionaries.
    """
    new_files_metadata = []
    if not service:
        logging.error("Google Drive service is not available.")
        return new_files_metadata
    if not folder_id:
        logging.error("DRIVE_FOLDER_ID is not set. Cannot list files.")
        # Consider raising an error or returning empty list based on desired behavior
        return new_files_metadata

    logging.info(f"Checking for new files in Google Drive folder ID: {folder_id}")
    page_token = None
    try:
        while True:
            # Construct the query to list files only in the specified folder
            # and exclude trashed files.
            # 'parents' in '{folder_id}' ensures we only get files directly in this folder.
            # 'trashed = false' excludes files in the trash.
            # We are interested in any file type, not just specific mimeTypes, unless specified.
            query = f"'{folder_id}' in parents and trashed = false"

            response = service.files().list(
                q=query,
                spaces='drive',
                # Fields to retrieve for each file. Add more if needed.
                # 'id, name, mimeType, createdTime, modifiedTime, webViewLink, parents'
                fields='nextPageToken, files(id, name, mimeType, createdTime, webViewLink, parents)',
                pageToken=page_token
            ).execute()

            files = response.get('files', [])
            logging.info(f"Found {len(files)} files in current page for folder '{folder_id}'.")

            for file_item in files:
                file_id = file_item.get('id')
                # Ensure the file is directly in the target folder (sometimes API might be tricky with shared items)
                # and not already processed.
                if file_id and file_id not in processed_file_ids:
                    # Check if the file's parent list explicitly contains the folder_id.
                    # This is a stricter check, though the query should handle it.
                    if folder_id in file_item.get('parents', []):
                        logging.info(f"New file detected: '{file_item.get('name')}' (ID: {file_id})")
                        new_files_metadata.append({
                            "id": file_id,
                            "name": file_item.get("name"),
                            "mimeType": file_item.get("mimeType"),
                            "createdTime": file_item.get("createdTime"),
                            "webViewLink": file_item.get("webViewLink")
                            # Add other metadata fields if needed
                        })
                    else:
                        logging.debug(f"File '{file_item.get('name')}' (ID: {file_id}) found by query but not directly in folder '{folder_id}'. Parents: {file_item.get('parents')}. Skipping.")

            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break # No more pages
        logging.info(f"Found a total of {len(new_files_metadata)} new files in folder '{folder_id}'.")

    except HttpError as error:
        logging.error(f'An HTTP error occurred while listing files: {error}')
        # Depending on the error, you might want to retry or handle specific status codes
    except Exception as e:
        logging.error(f'An unexpected error occurred while listing files: {e}')

    return new_files_metadata

def download_file_content(service, file_id: str) -> Optional[bytes]:
    """Downloads the content of a file given its Google Drive file ID."""
    if not service:
        logging.error("Google Drive service is not available for file download.")
        return None
    if not file_id:
        logging.error("File ID is not provided for download.")
        return None

    try:
        logging.info(f"Attempting to download content for file ID: {file_id}")
        # Request the file's content
        request = service.files().get_media(fileId=file_id)
        # response = request.execute() # This would save to a file if using MediaFileUpload
        # For getting content in memory:
        file_content = request.execute()
        logging.info(f"Successfully downloaded content for file ID: {file_id} (Size: {len(file_content)} bytes)")
        return file_content
    except HttpError as error:
        logging.error(f'An HTTP error occurred while downloading file ID {file_id}: {error}')
        # Check for specific errors, e.g., 404 for file not found, 403 for permission issues
        if error.resp.status == 404:
            logging.error(f"File ID {file_id} not found on Google Drive.")
        elif error.resp.status == 403:
            logging.error(f"Permission denied for downloading file ID {file_id}. Check scopes and file permissions.")
        return None
    except Exception as e:
        logging.error(f'An unexpected error occurred while downloading file ID {file_id}: {e}')
        return None

if __name__ == '__main__':
    # Example usage (for testing this module directly)
    # Ensure your .env file is set up with DRIVE_FOLDER_ID
    # and credentials.json is present or token.json is valid.
    print("Testing google_drive_utils.py...")
    if not DRIVE_FOLDER_ID:
        print("DRIVE_FOLDER_ID is not set in .env. Please set it for testing.")
    else:
        try:
            drive_service = get_drive_service()
            if drive_service:
                print(f"Successfully obtained Google Drive service.")
                # For testing, let's assume no files are processed yet
                test_processed_ids = set()
                print(f"Listing new files in folder: {DRIVE_FOLDER_ID} (assuming none processed yet)")
                new_files = list_new_files_in_folder(drive_service, DRIVE_FOLDER_ID, test_processed_ids)
                if new_files:
                    print(f"Found {len(new_files)} new files:")
                    for f_meta in new_files:
                        print(f"  - Name: {f_meta['name']}, ID: {f_meta['id']}, Link: {f_meta['webViewLink']}")
                        # Example: try downloading the first new PDF file found
                        if f_meta['mimeType'] == 'application/pdf' and len(new_files) > 0:
                            print(f"Attempting to download content of PDF: {f_meta['name']}")
                            pdf_content = download_file_content(drive_service, f_meta['id'])
                            if pdf_content:
                                print(f"Successfully downloaded {len(pdf_content)} bytes for {f_meta['name']}.")
                                # Here you could try parsing it with pdfplumber if testing
                            else:
                                print(f"Failed to download content for {f_meta['name']}.")
                            break # Just test one download
                else:
                    print("No new files found in the specified folder or an error occurred.")
            else:
                print("Could not obtain Google Drive service.")
        except FileNotFoundError as fnf_error:
            print(f"Test failed: {fnf_error}")
        except ConnectionError as conn_error:
            print(f"Test failed: {conn_error}")
        except Exception as e:
            print(f"An unexpected error occurred during testing: {e}")