import os, tempfile

os.environ["MODELFORGE_HOME"] = tempfile.mkdtemp(prefix="test-modelforge-", dir=".")
os.environ["MODELFORGE_ADMIN_TOKEN"] = "integration-test-token"
os.environ["DO_NOT_TRACK"] = "1"
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)
