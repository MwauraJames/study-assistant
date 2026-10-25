# app/ingestion/mongo_store.py
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING
import gridfs

from config import Settings

settings = Settings()


class MongoStore:
    def __init__(self):
        self.client = MongoClient(settings.mongo_uri)
        self.db = self.client[settings.mongo_db_name]
        self.fs = gridfs.GridFS(self.db)

        self.documents = self.db["documents"]
        self.chats = self.db["chats"]
        self.messages = self.db["messages"]

        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create indexes for fast lookup by user_id, subject, doc_id, and chat_id."""
        self.documents.create_index([("doc_id", ASCENDING)], unique=True)
        self.documents.create_index([("user_id", ASCENDING), ("subject", ASCENDING)])

        self.chats.create_index([("chat_id", ASCENDING)], unique=True)
        self.chats.create_index([("user_id", ASCENDING), ("subject", ASCENDING)])

        self.messages.create_index([("chat_id", ASCENDING), ("created_at", ASCENDING)])

    # ---------------- Document Storage (Raw + Parsed) ----------------

    def create_document_record(
        self,
        doc_id: str,
        user_id: str,
        subject: str,
        filename: str,
        raw_bytes: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """
        1. Saves the raw unprocessed file bytes in GridFS.
        2. Creates the metadata document in `documents` with status='processing'.
        """
        # If re-uploading the same doc_id, remove old GridFS binary first
        existing = self.documents.find_one({"doc_id": doc_id})
        if existing and existing.get("gridfs_id"):
            self.fs.delete(ObjectId(existing["gridfs_id"]))

        gridfs_id = self.fs.put(
            raw_bytes,
            filename=filename,
            user_id=user_id,
            subject=subject,
            doc_id=doc_id,
            content_type=content_type,
        )

        now = datetime.now(timezone.utc)
        self.documents.update_one(
            {"doc_id": doc_id},
            {
                "$set": {
                    "user_id": user_id,
                    "subject": subject,
                    "filename": filename,
                    "gridfs_id": str(gridfs_id),
                    "parsed_markdown": None,
                    "status": "processing",
                    "error": None,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return str(gridfs_id)

    def save_parsed_document(self, doc_id: str, parsed_markdown: str, num_leaves: int):
        """Store the parsed Markdown text and mark status as ready."""
        self.documents.update_one(
            {"doc_id": doc_id},
            {
                "$set": {
                    "parsed_markdown": parsed_markdown,
                    "num_leaves": num_leaves,
                    "status": "ready",
                    "error": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    def mark_document_failed(self, doc_id: str, error_msg: str):
        """Record ingestion failure reason in MongoDB."""
        self.documents.update_one(
            {"doc_id": doc_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error_msg,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    def get_document_status(self, doc_id: str) -> Optional[dict]:
        """Fetch document status (excludes heavy parsed_markdown field for speed)."""
        return self.documents.find_one(
            {"doc_id": doc_id},
            {"_id": 0, "parsed_markdown": 0},
        )

    def get_raw_file(self, doc_id: str) -> Optional[bytes]:
        """Retrieve the original unprocessed file bytes from GridFS."""
        doc = self.documents.find_one({"doc_id": doc_id}, {"gridfs_id": 1})
        if not doc or not doc.get("gridfs_id"):
            return None
        return self.fs.get(ObjectId(doc["gridfs_id"])).read()

    # ---------------- Continuous Chat History ----------------

    def ensure_chat_session(
        self,
        chat_id: str,
        user_id: str,
        subject: Optional[str] = None,
        title: Optional[str] = None,
    ):
        """Create a chat session if it doesn't exist yet."""
        now = datetime.now(timezone.utc)
        self.chats.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "user_id": user_id,
                    "subject": subject,
                    "title": title or "New Study Session",
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def add_message(self, chat_id: str, user_id: str, role: str, content: str):
        """Append a single 'user' or 'assistant' message to a chat."""
        now = datetime.now(timezone.utc)
        self.messages.insert_one(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": now,
            }
        )
        self.chats.update_one({"chat_id": chat_id}, {"$set": {"updated_at": now}})

    def get_recent_messages(self, chat_id: str, limit: int = settings.chat_history_limit) -> list[dict]:
        """
        Fetch the most recent N messages in chronological order (oldest -> newest)
        so they can be formatted into the LLM context.
        """
        cursor = (
            self.messages.find(
                {"chat_id": chat_id},
                {"_id": 0, "role": 1, "content": 1, "created_at": 1},
            )
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        messages = list(cursor)
        messages.reverse()  # Chronological order
        return messages

    def list_user_chats(self, user_id: str, subject: Optional[str] = None) -> list[dict]:
        """List all chat sessions for a user (optionally filtered by subject)."""
        query = {"user_id": user_id}
        if subject:
            query["subject"] = subject
        return list(
            self.chats.find(query, {"_id": 0}).sort("updated_at", DESCENDING)
        )