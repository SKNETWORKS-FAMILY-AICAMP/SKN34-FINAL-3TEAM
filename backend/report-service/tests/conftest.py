import os

os.environ.setdefault("INTERNAL_TOKEN", "test-token")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:1/")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")
