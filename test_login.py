import os, pyotp
from pathlib import Path
from dotenv import load_dotenv

# Explicit path avoids the find_dotenv frame-walk bug
load_dotenv(Path(__file__).parent / ".env")

totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
print(f"Generated TOTP: {totp}")

from angel_adapter import AngelBroker
b = AngelBroker().login()
print("✅ LOGIN OK")
print(f"   Client : {b.client_code}")
print(f"   Symbol : {b.symbol}")
print(f"   Token  : {b.token}")
print(f"   JWT    : {(b.jwt_token or '')[:40]}...")
print(f"   Feed   : {(b.feed_token or '')[:30]}...")
