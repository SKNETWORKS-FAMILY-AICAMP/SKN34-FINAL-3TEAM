"""격리 이벤트 운영 CLI. 신뢰된 report 운영 환경의 DB 권한으로만 실행한다."""

import argparse
import json
import logging
from uuid import UUID

from app.database import create_db_engine, create_session_factory, transaction
from app.outbox.repository import OutboxRepository


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument(
        "--limit", type=int, default=100, choices=range(1, 1001), metavar="1..1000"
    )
    retry = commands.add_parser("requeue")
    retry.add_argument("event_id", type=UUID)
    args = parser.parse_args(argv)
    engine = create_db_engine()
    factory, repository = create_session_factory(engine), OutboxRepository()
    try:
        with transaction(factory) as session:
            if args.command == "list":
                result = {"items": [dict(x) for x in repository.quarantined(session, args.limit)]}
            elif repository.requeue(session, args.event_id):
                result = {"eventId": str(args.event_id), "status": "REQUEUED"}
            else:
                result = {"eventId": str(args.event_id), "status": "NOT_REQUEUED"}
        print(json.dumps(result, default=str, ensure_ascii=False))
        if args.command == "requeue" and result["status"] == "REQUEUED":
            logging.getLogger(__name__).warning("Outbox manually requeued: id=%s", args.event_id)
        return 0 if args.command == "list" or result["status"] == "REQUEUED" else 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
