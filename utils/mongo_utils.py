import os
from pymongo import MongoClient, errors
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("MONGO_DATABASE_NAME", "google_drive_files")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "file_metadata")

if not MONGO_URI:
    logging.error("MONGO_URI not found in environment variables. Please set it in your .env file.")
    # You might want to raise an exception here or handle it appropriately
    # For now, we'll let it try to connect and fail if MONGO_URI is None

_client = None
_db = None
_collection = None

def get_mongo_collection():
    """
    Establishes a connection to MongoDB and returns the collection object.
    Uses a global client to avoid reconnecting multiple times.
    """
    global _client, _db, _collection
    if _collection is None:
        try:
            if not MONGO_URI:
                raise ValueError("MongoDB URI is not configured. Please set MONGO_URI in your .env file.")

            logging.info(f"Connecting to MongoDB at {MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI}...")
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) # 5 second timeout
            # The ismaster command is cheap and does not require auth.
            _client.admin.command('ismaster')
            logging.info("Successfully connected to MongoDB.")
            _db = _client[DATABASE_NAME]
            _collection = _db[COLLECTION_NAME]
            # Create an index on file_id to speed up checks and prevent duplicates if needed
            # This ensures that lookups for file_id are fast.
            # `unique=True` could be added if you want to strictly prevent duplicate file_id entries,
            # but the current logic in main.py already checks before inserting.
            _collection.create_index("id", name="file_id_index")
            logging.info(f"Using database '{DATABASE_NAME}' and collection '{COLLECTION_NAME}'.")
        except errors.ServerSelectionTimeoutError as err:
            logging.error(f"MongoDB connection failed: Server timeout - {err}")
            _client = None # Reset client so it can try to reconnect next time
            _db = None
            _collection = None
            raise ConnectionError(f"Could not connect to MongoDB: {err}") from err
        except errors.ConnectionFailure as err:
            logging.error(f"MongoDB connection failed: Connection failure - {err}")
            _client = None
            _db = None
            _collection = None
            raise ConnectionError(f"Could not connect to MongoDB: {err}") from err
        except ValueError as err:
            logging.error(str(err))
            raise err
        except Exception as e:
            logging.error(f"An unexpected error occurred while connecting to MongoDB: {e}")
            _client = None
            _db = None
            _collection = None
            raise ConnectionError(f"Unexpected error connecting to MongoDB: {e}") from e
    return _collection

def file_exists_in_db(file_id: str) -> bool:
    """Checks if a file with the given Google Drive file ID already exists in the database."""
    try:
        collection = get_mongo_collection()
        if collection is None:
            logging.error("Cannot check if file exists: MongoDB collection is not available.")
            return False # Or raise an exception
        return collection.count_documents({"id": file_id}) > 0
    except ConnectionError:
        logging.error("Cannot check if file exists due to MongoDB connection error.")
        # Depending on desired behavior, you might want to return True to prevent processing
        # or False to allow retries later. For now, returning False.
        return False
    except Exception as e:
        logging.error(f"Error checking if file ID '{file_id}' exists in DB: {e}")
        return False # Default to false to potentially allow reprocessing if it's a transient error

def insert_file_metadata(metadata: dict):
    """Inserts file metadata into the MongoDB collection."""
    try:
        collection = get_mongo_collection()
        if collection is None:
            logging.error(f"Cannot insert metadata for file '{metadata.get('name')}': MongoDB collection is not available.")
            return None # Or raise an exception

        logging.info(f"Inserting metadata for file: {metadata.get('name')} (ID: {metadata.get('id')})")
        result = collection.insert_one(metadata)
        logging.info(f"Successfully inserted metadata with MongoDB ID: {result.inserted_id}")
        return result.inserted_id
    except ConnectionError:
        logging.error(f"Cannot insert metadata for file '{metadata.get('name')}' due to MongoDB connection error.")
        return None
    except errors.PyMongoError as e:
        logging.error(f"MongoDB error inserting metadata for file '{metadata.get('name')}': {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error inserting metadata for file '{metadata.get('name')}': {e}")
        return None

def get_all_processed_file_ids() -> set:
    """Retrieves all Google Drive file IDs that have already been processed and stored in MongoDB."""
    processed_ids = set()
    try:
        collection = get_mongo_collection()
        if collection is None:
            logging.warning("Cannot get processed file IDs: MongoDB collection is not available.")
            return processed_ids # Return empty set, will cause reprocessing if connection recovers

        for doc in collection.find({}, {"id": 1, "_id": 0}): # Only fetch the 'id' field
            if "id" in doc:
                processed_ids.add(doc["id"])
        logging.info(f"Retrieved {len(processed_ids)} processed file IDs from database.")
    except ConnectionError:
        logging.error("Cannot get processed file IDs due to MongoDB connection error.")
        # Return empty set, which means if connection is down, all files might be re-checked
        # This is safer than returning None or raising an exception that stops the main loop
    except Exception as e:
        logging.error(f"Error retrieving processed file IDs from DB: {e}")
    return processed_ids

def close_mongo_connection():
    """Closes the MongoDB connection if it's open."""
    global _client
    if _client:
        logging.info("Closing MongoDB connection.")
        _client.close()
        _client = None

if __name__ == '__main__':
    # Example usage (for testing this module directly)
    # Ensure your .env file is set up with MONGO_URI, etc.
    print("Testing mongo_utils.py...")
    try:
        collection = get_mongo_collection()
        if collection is not None:
            print(f"Successfully connected to collection: {collection.name}")

            # Test insert
            test_metadata = {
                "id": "test_file_id_123",
                "name": "test_document.txt",
                "mimeType": "text/plain",
                "createdTime": "2023-01-01T12:00:00.000Z",
                "webViewLink": "https://example.com/test_document.txt"
            }
            if not file_exists_in_db("test_file_id_123"):
                print(f"Attempting to insert: {test_metadata['name']}")
                insert_id = insert_file_metadata(test_metadata)
                if insert_id:
                    print(f"Inserted test metadata with DB ID: {insert_id}")
                else:
                    print("Failed to insert test metadata.")
            else:
                print(f"Test file '{test_metadata['name']}' already exists in DB.")

            # Test exists
            print(f"Does 'test_file_id_123' exist? {file_exists_in_db('test_file_id_123')}")
            print(f"Does 'non_existent_file_id' exist? {file_exists_in_db('non_existent_file_id')}")

            # Test get all processed IDs
            processed_ids = get_all_processed_file_ids()
            print(f"Processed file IDs: {processed_ids}")

            # Clean up test data (optional)
            # if collection is not None:
            #     del_result = collection.delete_one({"id": "test_file_id_123"})
            #     print(f"Deleted test document: {del_result.deleted_count}")

        else:
            print("Could not establish MongoDB connection for testing.")

    except ConnectionError as ce:
        print(f"Test failed due to connection error: {ce}")
    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        close_mongo_connection()