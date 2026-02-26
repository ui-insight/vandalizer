#!/usr/bin/env python3
"""
Test script to generate an API token for a user.
Run this to create a token for testing the Chrome extension.
"""

from app import app
from app.models import User

def generate_token_for_user(user_id):
    """Generate an API token for the specified user."""
    with app.app_context():
        user = User.objects(user_id=user_id).first()

        if not user:
            print(f"❌ User '{user_id}' not found")
            print("\nAvailable users:")
            for u in User.objects():
                print(f"  - {u.user_id} ({u.name or 'No name'})")
            return

        token = user.generate_api_token()

        print("✅ API Token generated successfully!")
        print(f"\n{'='*60}")
        print(f"User ID: {user.user_id}")
        print(f"Name: {user.name or 'Not set'}")
        print(f"Email: {user.email or 'Not set'}")
        print(f"{'='*60}")
        print(f"\n🔑 API Token:")
        print(f"{token}")
        print(f"\n{'='*60}")
        print("\n📋 Chrome Extension Configuration:")
        print(f"  Backend URL: http://localhost:5000")
        print(f"  User Token: {token}")
        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_api_token.py <user_id>")
        print("\nExample: python test_api_token.py admin")
        sys.exit(1)

    user_id = sys.argv[1]
    generate_token_for_user(user_id)
