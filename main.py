import time
import logging
import os
from dotenv import load_dotenv
import io # For handling bytes data as a file-like object
import pdfplumber # For parsing PDF text

import utils.google_drive_utils as google_drive_utils
import utils.mongo_utils as mongo_utils

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# How often to check Google Drive for new files (in seconds)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 60 * 1)) 

def main_loop():
    """
    Main loop to periodically check for new files and process them.
    """
    logging.info("Starting Google Drive Monitor application...")

    # Initial connection attempts
    try:
        drive_service = google_drive_utils.get_drive_service()
        if not drive_service:
            logging.error("Failed to initialize Google Drive service. Exiting.")
            return

        # Initialize MongoDB connection and get collection
        # This will also raise ConnectionError if it fails, caught below
        mongo_collection = mongo_utils.get_mongo_collection()
        if mongo_collection is None: # Correct way to check for a None collection object
            logging.error("Failed to initialize MongoDB collection. Exiting.")
            return

    except FileNotFoundError as e: # Specifically for credentials.json missing
        logging.error(f"Configuration error: {e}. Please ensure credentials.json is set up. Exiting.")
        return
    except ConnectionError as e: # Catches connection errors from both utils
        logging.error(f"Connection error during initialization: {e}. Exiting.")
        return
    except Exception as e:
        logging.error(f"Unexpected error during initialization: {e}. Exiting.")
        return

    folder_id_to_monitor = os.getenv('DRIVE_FOLDER_ID')
    if not folder_id_to_monitor:
        logging.error("DRIVE_FOLDER_ID is not set in the .env file. Please specify the folder to monitor. Exiting.")
        return

    logging.info(f"Successfully initialized. Monitoring folder ID: {folder_id_to_monitor}")
    logging.info(f"Will check for new files every {CHECK_INTERVAL_SECONDS} seconds.")

    try:
        while True:
            logging.info("Checking for new files...")
            try:
                # Get IDs of files already processed to avoid duplicates
                processed_ids = mongo_utils.get_all_processed_file_ids()

                # List new files from Google Drive
                # Ensure drive_service is still valid or re-authenticate if necessary (get_drive_service handles refresh)
                # For simplicity, we re-get service if a major error occurs, but robust apps might have more nuanced refresh.
                current_drive_service = google_drive_utils.get_drive_service() # Handles token refresh
                if not current_drive_service:
                    logging.error("Google Drive service became unavailable. Attempting to reconnect on next cycle.")
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    continue


                new_files = google_drive_utils.list_new_files_in_folder(
                    current_drive_service,
                    folder_id_to_monitor,
                    processed_ids
                )

                if new_files:
                    logging.info(f"Found {len(new_files)} new file(s) to process.")
                    for file_metadata in new_files:
                        # Basic metadata is already in file_metadata from list_new_files_in_folder
                        # file_metadata = {"id": ..., "name": ..., "mimeType": ..., "createdTime": ..., "webViewLink": ...}

                        if file_metadata.get("mimeType") == "application/pdf":
                            logging.info(f"File '{file_metadata['name']}' is a PDF. Attempting to download and extract text.")
                            pdf_content_bytes = google_drive_utils.download_file_content(current_drive_service, file_metadata["id"])
                            if pdf_content_bytes:
                                extracted_text = ""
                                try:
                                    # pdfplumber needs a file-like object or path, so use io.BytesIO for in-memory bytes
                                    with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
                                        for page in pdf.pages:
                                            page_text = page.extract_text()
                                            if page_text:
                                                extracted_text += page_text + "\n"
                                    file_metadata["extracted_pdf_text"] = extracted_text.strip()
                                    logging.info(f"Successfully extracted text from PDF '{file_metadata['name']}'. Length: {len(extracted_text)} chars.")
                                except Exception as e:
                                    logging.error(f"Failed to parse PDF content for '{file_metadata['name']}': {e}")
                                    file_metadata["extracted_pdf_text"] = None # Or some error message
                                    file_metadata["pdf_parsing_error"] = str(e)
                            else:
                                logging.warning(f"Could not download content for PDF '{file_metadata['name']}'. No text will be extracted.")
                                file_metadata["extracted_pdf_text"] = None
                                file_metadata["pdf_download_error"] = "Failed to download content"

                        # Now, insert the potentially augmented metadata
                        if not mongo_utils.file_exists_in_db(file_metadata["id"]):
                            mongo_utils.insert_file_metadata(file_metadata)
                        else:
                            logging.warning(f"File '{file_metadata['name']}' (ID: {file_metadata['id']}) "
                                            "was listed as new but already exists in DB. Skipping insertion.")
                else:
                    logging.info("No new files found in this check.")

            except ConnectionError as ce: # Catch connection errors from utils during the loop
                logging.error(f"A connection error occurred during the check cycle: {ce}. Will retry after interval.")
            except Exception as e:
                logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
                # Depending on the error, you might want to implement more sophisticated retry logic
                # or stop the loop for critical errors.

            logging.info(f"Waiting for {CHECK_INTERVAL_SECONDS} seconds before next check...")
            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("Application interrupted by user (Ctrl+C). Shutting down...")
    finally:
        logging.info("Closing connections...")
        mongo_utils.close_mongo_connection()
        logging.info("Google Drive Monitor application finished.")

if __name__ == "__main__":
    # Before starting the main loop, ensure essential configurations are present
    # to provide early feedback to the user.
    if not os.getenv("MONGO_URI"):
        logging.error("CRITICAL: MONGO_URI is not set in .env file. Application cannot start.")
    elif not os.getenv("DRIVE_FOLDER_ID"):
        logging.error("CRITICAL: DRIVE_FOLDER_ID is not set in .env file. Application cannot start.")
    elif not os.path.exists(google_drive_utils.CREDENTIALS_PATH):
         logging.error(f"CRITICAL: Google API credentials file '{google_drive_utils.CREDENTIALS_PATH}' not found. Application cannot start.")
    else:
        main_loop()