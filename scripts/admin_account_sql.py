"""Print SQL that registers, updates or disables an admin ID/password login (#369).

Admins have no signup. An operator runs this script and pipes the SQL into psql for core_db:

    python scripts/admin_account_sql.py --login-id ops-kim --name 김운영 --permissions ALL | psql "$CORE_DB_URL"
    python scripts/admin_account_sql.py --login-id ops-kim --disable | psql "$CORE_DB_URL"

Running it again for the same ID sets a new password and clears the failure lock. --permissions, when given,
replaces the account's permissions; when omitted, existing permissions are kept. The password is read with
getpass, or from ADMIN_PASSWORD for non-interactive use, and only its PBKDF2 hash appears in the output.
"""
import argparse
import base64
import getpass
import hashlib
import os
import secrets
import sys
import uuid

PERMISSIONS = ("CONTENT", "PAYMENT_VIEW", "PAYMENT_REFUND", "SERVICE_OPS")
# Must match core guardianship/service/PinHasher.kt.
ITERATIONS = 600_000
PASSWORD_MIN, PASSWORD_MAX, LOGIN_ID_MAX = 12, 128, 254


def password_hash(password, salt=None):
    salt = salt if salt is not None else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, 32)
    return "$".join(("pbkdf2-sha256", str(ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(derived).decode()))


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def login_id(raw):
    value = raw.strip()
    if not value or len(value) > LOGIN_ID_MAX or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise argparse.ArgumentTypeError(f"login ID must be 1-{LOGIN_ID_MAX} characters without spaces")
    return value


def permissions(raw):
    values = PERMISSIONS if raw.strip().upper() == "ALL" else tuple(dict.fromkeys(p.strip().upper() for p in raw.split(",") if p.strip()))
    unknown = [p for p in values if p not in PERMISSIONS]
    if unknown or not values:
        raise argparse.ArgumentTypeError(f"permissions must be ALL or a comma list of {', '.join(PERMISSIONS)}")
    return values


def check_password(password):
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise ValueError(f"password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters")
    return password


def upsert_sql(login, name, perms, hashed, account_id=None):
    account = literal(str(account_id or uuid.uuid4()))
    lid = literal(login)
    owner = f"(SELECT id FROM user_account WHERE login_id = {lid})"
    lines = [
        "BEGIN;",
        "DO $$ BEGIN",
        f"  IF EXISTS (SELECT 1 FROM user_account WHERE login_id = {lid} AND (role <> 'ADMIN' OR status <> 'ACTIVE')) THEN",
        "    RAISE EXCEPTION 'login ID belongs to a non-admin or inactive account';",
        "  END IF;",
        "END $$;",
        "INSERT INTO user_account(id, role, login_id, password_hash, display_name, status, is_demo,",
        "                         oauth_provider, oauth_subject, created_at, updated_at)",
        f"VALUES ({account}, 'ADMIN', {lid}, NULL, {literal(name)}, 'ACTIVE', false, NULL, NULL, now(), now())",
        "ON CONFLICT (login_id) DO NOTHING;",
    ]
    if perms is not None:
        values = ", ".join(f"({literal(p)})" for p in perms)
        lines += [
            f"DELETE FROM admin_permission WHERE user_id = {owner} AND permission NOT IN ({', '.join(literal(p) for p in perms)});",
            "INSERT INTO admin_permission(user_id, permission, granted_by, granted_at)",
            f"SELECT u.id, v.permission, u.id, now() FROM user_account u, (VALUES {values}) AS v(permission)",
            f"WHERE u.login_id = {lid} ON CONFLICT DO NOTHING;",
        ]
    lines += [
        "INSERT INTO admin_credential(user_id, password_hash, failed_count, locked_until, created_at, updated_at)",
        f"SELECT id, {literal(hashed)}, 0, NULL, now(), now() FROM user_account WHERE login_id = {lid}",
        "ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash, failed_count = 0,",
        "    locked_until = NULL, updated_at = EXCLUDED.updated_at;",
        "COMMIT;",
    ]
    return "\n".join(lines) + "\n"


def disable_sql(login):
    owner = f"(SELECT id FROM user_account WHERE login_id = {literal(login)} AND role = 'ADMIN')"
    return "\n".join([
        "BEGIN;",
        f"DELETE FROM admin_credential WHERE user_id = {owner};",
        f"UPDATE auth_session SET revoked_at = now() WHERE user_id = {owner} AND revoked_at IS NULL;",
        "COMMIT;",
    ]) + "\n"


def read_password():
    if "ADMIN_PASSWORD" in os.environ:
        return check_password(os.environ["ADMIN_PASSWORD"])
    first = check_password(getpass.getpass("admin password: "))
    if getpass.getpass("confirm password: ") != first:
        raise ValueError("passwords do not match")
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--login-id", required=True, type=login_id)
    parser.add_argument("--name", help="display name (default: login ID)")
    parser.add_argument("--permissions", type=permissions, help="ALL or comma list; omit to keep current permissions")
    parser.add_argument("--disable", action="store_true", help="remove password login and end the account's sessions")
    args = parser.parse_args(argv)
    # psql reads UTF-8; a Windows pipe would otherwise encode Korean names in the console code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.disable:
        sys.stdout.write(disable_sql(args.login_id))
        return 0
    try:
        password = read_password()
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.write(upsert_sql(args.login_id, (args.name or args.login_id).strip(), args.permissions, password_hash(password)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
