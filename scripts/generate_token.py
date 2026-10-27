#!/usr/bin/env python3
"""Generate a LiveKit room token for browser testing (LiveKit Cloud free tier)."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LiveKit access token")
    parser.add_argument("--room", default="demo-room", help="Room name")
    parser.add_argument("--identity", default="customer", help="Participant identity")
    args = parser.parse_args()

    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([url, api_key, api_secret]):
        print(
            "Missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET.\n"
            "Sign up free at https://cloud.livekit.io",
            file=sys.stderr,
        )
        sys.exit(1)

    from livekit.api import AccessToken, VideoGrants

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(args.identity)
        .with_name(args.identity)
        .with_grants(VideoGrants(room_join=True, room=args.room))
        .to_jwt()
    )

    print(f"LIVEKIT_URL={url}")
    print(f"ROOM={args.room}")
    print(f"TOKEN={token}")


if __name__ == "__main__":
    main()
