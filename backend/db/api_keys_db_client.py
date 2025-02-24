import os
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy').setLevel(logging.ERROR)

class APIEncryptedDatabase:
    # Load environment variables and define constants
    load_dotenv('backend/db/db_paths.env')

    DATABASE_URL = os.getenv("API_KEYS_DB_PATH")
    KEY_FILE = "backend/db/encryption_key.key"

    # Initialize database engine, session, and ORM base
    engine = sa.create_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine)
    Base = declarative_base()
    cipher = None  # Placeholder for encryption cipher

    # Database Model
    class APIKeyStore(Base):
        __tablename__ = "api_keys"

        id = sa.Column(sa.Integer, primary_key=True)
        name = sa.Column(sa.String, unique=True, nullable=False)
        api_key = sa.Column(sa.String, nullable=False)
        secret_key = sa.Column(sa.String, nullable=True)
        api_metadata = sa.Column(sa.String, nullable=True)

        def __init__(self, name: str, api_key: str, secret_key: str = None, api_metadata: str = None):
            self.name = name
            self.api_key = APIEncryptedDatabase.cipher.encrypt(api_key.encode()).decode()
            self.secret_key = APIEncryptedDatabase.cipher.encrypt(secret_key.encode()).decode() if secret_key else None
            self.api_metadata = APIEncryptedDatabase.cipher.encrypt(api_metadata.encode()).decode() if api_metadata else None

        def decrypt_data(self):
            try:
                self.api_key = APIEncryptedDatabase.cipher.decrypt(self.api_key.encode()).decode()
                if self.secret_key:
                    self.secret_key = APIEncryptedDatabase.cipher.decrypt(self.secret_key.encode()).decode()
                if self.api_metadata:
                    self.api_metadata = APIEncryptedDatabase.cipher.decrypt(self.api_metadata.encode()).decode()
            except InvalidToken:
                raise ValueError("APIEncryptedDatabase :: ❌ Decryption failed. Invalid encryption key.")

    @classmethod
    def load_or_generate_key(cls):
        """Loads the encryption key from a file or generates a new one."""
        if not os.path.exists(cls.KEY_FILE):
            key = Fernet.generate_key()
            with open(cls.KEY_FILE, "wb") as key_file:
                key_file.write(key)
            print("APIEncryptedDatabase :: 🔑 New encryption key generated and saved.")
        else:
            print("APIEncryptedDatabase :: ✅ Encryption key already exists.")

        # Load the key
        with open(cls.KEY_FILE, "rb") as key_file:
            return key_file.read()

    @classmethod
    def init_cipher(cls):
        """Initializes the encryption cipher."""
        cls.cipher = Fernet(cls.load_or_generate_key())

    @classmethod
    def init_db(cls):
        """Creates the database if it doesn't exist, otherwise does nothing."""
        db_file = cls.DATABASE_URL.replace("sqlite:///", "")
        if os.path.exists(db_file):
            print("APIEncryptedDatabase :: ✅ Database already exists.")
        else:
            print("APIEncryptedDatabase :: 📦 Creating database...")
            cls.Base.metadata.create_all(cls.engine)
            print("APIEncryptedDatabase :: ✅ Database initialized.")

    @classmethod
    def insert_api_key(cls, name: str, api_key: str, secret_key: str = None, api_metadata: str = None):
        """Inserts a new API key into the database."""
        session = cls.Session()
        if session.query(cls.APIKeyStore).filter_by(name=name).first():
            print(f"APIEncryptedDatabase :: ⚠️ API Key with name '{name}' already exists.")
            session.close()
            return
        new_key = cls.APIKeyStore(name=name, api_key=api_key, secret_key=secret_key, api_metadata=api_metadata)
        session.add(new_key)
        session.commit()
        session.close()
        print(f"APIEncryptedDatabase :: ✅ API Key '{name}' added successfully.")

    @classmethod
    def get_api_keys(cls):
        """Retrieves and decrypts API keys from the database."""
        session = cls.Session()
        keys = session.query(cls.APIKeyStore).all()
        for key in keys:
            key.decrypt_data()
        session.close()
        return keys

    @classmethod
    def get_api_key_by_name(cls, name: str):
        """Retrieves and decrypts an API key by name."""
        session = cls.Session()
        key = session.query(cls.APIKeyStore).filter_by(name=name).first()
        if key:
            key.decrypt_data()
            session.close()
            return key
        session.close()
        print(f"APIEncryptedDatabase :: ⚠️ No API Key found with name '{name}'.")
        return None

    @classmethod
    def update_api_key(cls, name: str, new_api_key: str = None, new_secret_key: str = None, new_metadata: str = None):
        """Updates an existing API key by name."""
        session = cls.Session()
        key = session.query(cls.APIKeyStore).filter_by(name=name).first()
        if not key:
            print(f"APIEncryptedDatabase :: ⚠️ No API Key found with name '{name}'.")
            session.close()
            return

        if new_api_key:
            key.api_key = cls.cipher.encrypt(new_api_key.encode()).decode()
        if new_secret_key:
            key.secret_key = cls.cipher.encrypt(new_secret_key.encode()).decode()
        if new_metadata is not None:
            key.api_metadata = new_metadata

        session.commit()
        session.close()
        print(f"APIEncryptedDatabase :: ✅ API Key '{name}' updated successfully.")

    @classmethod
    def delete_api_key(cls, name: str):
        """Deletes an API key by name."""
        session = cls.Session()
        key = session.query(cls.APIKeyStore).filter_by(name=name).first()
        if not key:
            print(f"APIEncryptedDatabase :: ⚠️ No API Key found with name '{name}'.")
            session.close()
            return

        session.delete(key)
        session.commit()
        session.close()
        print(f"APIEncryptedDatabase :: 🗑️ API Key '{name}' deleted successfully.")
