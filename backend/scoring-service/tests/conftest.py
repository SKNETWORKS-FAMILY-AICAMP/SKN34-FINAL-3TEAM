import os

os.environ.setdefault("INTERNAL_TOKEN", "test-token")
# 모든 호출자에 같은 토큰. 경로 허용 목록은 그대로 적용됨
os.environ.setdefault("INTERNAL_TOKEN_AI", "test-token")
os.environ.setdefault("INTERNAL_TOKEN_CORE", "test-token")
os.environ.setdefault("INTERNAL_TOKEN_OPS", "test-token")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:1/")
os.environ.setdefault("CORE_URL", "http://127.0.0.1:1")
