from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Define the base class for our ORM model
Base = declarative_base()


# Define the model class for the table
class ApiCredentials(Base):
    __tablename__ = 'api_credentials'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    secret_key = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata = Column(String, nullable=True)  # This is the extra field

    def __repr__(self):
        return f"<ApiCredentials(name={self.name}, api_key={self.api_key}, secret_key={self.secret_key}, created_at={self.created_at}, metadata={self.metadata})>"


# Create the DB client class
class DBClient:
    def __init__(self, db_url: str, password: str):
        # Create an encrypted SQLAlchemy engine using SQLCipher
        self.engine = create_engine(f"sqlite+sqlcipher:///{db_url}?cipher=aes-256-cbc&key={password}")
        Base.metadata.create_all(self.engine)  # Create tables if they don't exist
        self.Session = sessionmaker(bind=self.engine)

    def insert(self, name: str, api_key: str, secret_key: str, metadata: str = None):
        """Insert a new record into the api_credentials table."""
        session = self.Session()
        new_record = ApiCredentials(
            name=name,
            api_key=api_key,
            secret_key=secret_key,
            metadata=metadata
        )
        session.add(new_record)
        session.commit()
        session.close()
        print(f"Inserted new record: {new_record}")

    def update(self, record_id: int, name: str = None, api_key: str = None, secret_key: str = None,
               metadata: str = None):
        """Update an existing record by ID."""
        session = self.Session()
        record = session.query(ApiCredentials).filter(ApiCredentials.id == record_id).first()

        if record:
            if name:
                record.name = name
            if api_key:
                record.api_key = api_key
            if secret_key:
                record.secret_key = secret_key
            if metadata is not None:  # If provided, update metadata
                record.metadata = metadata
            session.commit()
            print(f"Updated record: {record}")
        else:
            print(f"No record found with ID {record_id}")

        session.close()

    def delete(self, record_id: int):
        """Delete a record by ID."""
        session = self.Session()
        record = session.query(ApiCredentials).filter(ApiCredentials.id == record_id).first()

        if record:
            session.delete(record)
            session.commit()
            print(f"Deleted record: {record}")
        else:
            print(f"No record found with ID {record_id}")

        session.close()

    def get_all(self):
        """Fetch all records from the api_credentials table."""
        session = self.Session()
        records = session.query(ApiCredentials).all()
        session.close()
        return records


# Example usage
if __name__ == "__main__":
    # DB setup
    db_url = 'encrypted_db.db'  # Path to your encrypted database
    db_password = 'your_encryption_password'  # The encryption key for the database
    client = DBClient(db_url, db_password)

    # Insert a new record
    client.insert(name="MyApp", api_key="my_api_key", secret_key="my_secret_key", metadata="Some extra data")

    # Update a record by ID (example with id 1)
    client.update(record_id=1, name="UpdatedApp", api_key="new_api_key", metadata="Updated extra data")

    # Fetch all records
    records = client.get_all()
    for record in records:
        print(record)

    # Delete a record by ID (example with id 1)
    client.delete(record_id=1)