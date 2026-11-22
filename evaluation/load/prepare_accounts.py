"""Create load-test parent accounts through the public API and write the k6 secrets file (#415).

Each account: ID/password signup -> TERMS/PRIVACY consent -> children (GUARDIAN consent) -> one student device
(pairing code + registration) -> child PIN. Accounts are is_demo only where core runs with
AUTH_NEW_ACCOUNT_DEMO=true (the AWS demo does). Passwords, PINs and device cookies go only to the secrets file, which
must be outside the repository; nothing secret is printed.

    python evaluation/load/prepare_accounts.py --base-url http://localhost:5173 --count 4 \\
        --secrets C:/Users/<user>/sagomungchi-load/secrets.json

Signups are limited per client IP (default 5 per 10 minutes). With --wait the script sleeps and retries on 429.
Running again with the same --prefix and --secrets appends only the accounts that are not in the file yet.

With --families <json> (#808 dummy families, infrastructure/aws/dummy854-families.json) the login IDs, parent names,
child nicknames and grades come from the file, and each child also gets the optional COMMUNITY consent. The password is
written to the secrets file right after signup, so a run that stops halfway resumes on the next run (login, then only
the missing consents, children, device and PINs). --count limits it to the first N families.
"""
import argparse
import http.cookiejar
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ApiFailure(RuntimeError):
    def __init__(self, step, status, code):
        super().__init__(f"{step} failed: HTTP {status} {code}")
        self.status = status
        self.code = code


class Client:
    """One account's browser-like session: cookie jar plus the Origin/X-Requested-With headers core requires."""

    def __init__(self, base_url, host=None, origin=None):
        self.base = base_url.rstrip("/")
        self.origin = (origin or self.base).rstrip("/")
        self.host = host
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.token = None

    def call(self, step, method, path, body=None, headers=None):
        request = urllib.request.Request(self.base + "/api/v1" + path, method=method,
                                         data=None if body is None else json.dumps(body).encode("utf-8"))
        request.add_header("Content-Type", "application/json")
        request.add_header("Origin", self.origin)
        if self.host:
            request.add_header("Host", self.host)
        request.add_header("X-Requested-With", "XMLHttpRequest")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            try:
                code = json.loads(error.read() or b"{}").get("code", "")
            except ValueError:
                code = ""
            raise ApiFailure(step, error.code, code) from None

    def cookie(self, name):
        return next((c.value for c in self.jar if c.name == name), None)


def valid_pin(pin):
    digits = [int(d) for d in pin]
    same = len(set(digits)) == 1
    run = any(all(b - a == step for a, b in zip(digits, digits[1:])) for step in (1, -1))
    return not same and not run


def new_pin():
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(6))
        if valid_pin(pin):
            return pin


def current_documents(client):
    items = client.call("consent documents", "GET", "/consent-documents")["items"]
    return {d["kind"]: {"documentId": d["documentId"], "version": d["version"], "agreed": True} for d in items}


def signup(client, login_id, password, wait, name=None):
    while True:
        try:
            return client.call("signup", "POST", "/auth/parent/signup",
                               {"loginId": login_id, "password": password, "name": name or f"부하시험 {login_id}"})
        except ApiFailure as failure:
            if failure.code != "SIGNUP_RATE_LIMITED" or not wait:
                raise
            print(f"{login_id}: signup limit reached, waiting 60s", flush=True)
            time.sleep(60)


def prepare(base_url, login_id, children, grade, wait, host=None, origin=None):
    client = Client(base_url, host, origin)
    password = secrets.token_urlsafe(18)
    issued = signup(client, login_id, password, wait)
    client.token = issued["accessToken"]
    documents = current_documents(client)
    client.call("account consents", "POST", "/me/consents", {"consents": [documents["TERMS"], documents["PRIVACY"]]})
    birth_year = date.today().year - grade - 6
    kids = []
    for n in range(children):
        child = client.call("child registration", "POST", "/children", {
            "nickname": f"부하{n + 1}", "grade": grade, "birthYear": birth_year, "consents": [documents["GUARDIAN"]]})
        kids.append({"childId": child["id"]})
    pairing = client.call("pairing code", "POST", "/student-devices/pairings", {"childIds": [k["childId"] for k in kids]})
    client.call("device registration", "POST", "/auth/student/devices", {"pairingCode": pairing["pairingCode"], "label": "부하 시험 기기"})
    device = client.cookie("student_device")
    if not device:
        raise ApiFailure("device registration", 201, "NO_DEVICE_COOKIE")
    for kid in kids:
        kid["pin"] = new_pin()
        client.call("child PIN", "PUT", f"/children/{kid['childId']}/pin", {"pin": kid["pin"]})
    return {"loginId": login_id, "password": password, "deviceCookie": device, "children": kids}


def family_ready(entry, family):
    pins = {k.get("nickname") for k in entry.get("children", []) if k.get("pin")}
    return bool(entry.get("deviceCookie")) and all(c["nickname"] in pins for c in family["children"])


def prepare_family(base_url, family, entry, save, wait, host=None, origin=None):
    """One #808 family. Every step checks what already exists, so a stopped run can be repeated."""
    client = Client(base_url, host, origin)
    if entry is None:
        entry = {"loginId": family["loginId"], "password": secrets.token_urlsafe(18), "children": []}
        issued = signup(client, entry["loginId"], entry["password"], wait, family["name"])
        save(entry)
    else:
        issued = client.call("login", "POST", "/auth/parent/login",
                             {"loginId": entry["loginId"], "password": entry["password"]})
    client.token = issued["accessToken"]
    documents = current_documents(client)
    if "COMMUNITY" not in documents:
        raise ApiFailure("consent documents", 200, "NO_COMMUNITY_DOCUMENT")
    # Re-sending the same account consent is a no-op (api-spec 2.1).
    client.call("account consents", "POST", "/me/consents", {"consents": [documents["TERMS"], documents["PRIVACY"]]})
    have = {c["nickname"]: c["id"] for c in client.call("children", "GET", "/children")["items"]}
    kids = {k["nickname"]: k for k in entry["children"] if k.get("nickname")}
    for spec in family["children"]:
        if spec["nickname"] not in have:
            child = client.call("child registration", "POST", "/children", {
                "nickname": spec["nickname"], "grade": spec["grade"], "birthYear": date.today().year - spec["grade"] - 6,
                "consents": [documents["GUARDIAN"]]})
            have[spec["nickname"]] = child["id"]
        kid = kids.setdefault(spec["nickname"], {"nickname": spec["nickname"]})
        kid["childId"] = have[spec["nickname"]]
        # COMMUNITY is optional and cannot be given at registration (one GUARDIAN item only); the same choice again is a no-op.
        client.call("community consent", "POST", "/me/consents",
                    {"childId": kid["childId"], "consents": [documents["COMMUNITY"]]})
    entry["children"] = [kids[c["nickname"]] for c in family["children"]]
    save(entry)
    if not entry.get("deviceCookie"):
        pairing = client.call("pairing code", "POST", "/student-devices/pairings",
                              {"childIds": [k["childId"] for k in entry["children"]]})
        client.call("device registration", "POST", "/auth/student/devices",
                    {"pairingCode": pairing["pairingCode"], "label": "더미 가족 기기"})
        entry["deviceCookie"] = client.cookie("student_device")
        if not entry["deviceCookie"]:
            raise ApiFailure("device registration", 201, "NO_DEVICE_COOKIE")
        save(entry)
    for kid in entry["children"]:
        if not kid.get("pin"):
            pin = new_pin()
            client.call("child PIN", "PUT", f"/children/{kid['childId']}/pin", {"pin": pin})
            kid["pin"] = pin
            save(entry)
    return entry


def run_families(args, accounts, write):
    families = json.loads(args.families.read_text(encoding="utf-8"))["families"][:args.count]
    by_id = {a.get("loginId"): a for a in accounts}

    def save(entry):
        if entry["loginId"] not in by_id:
            by_id[entry["loginId"]] = entry
            accounts.append(entry)
        write()

    for family in families:
        entry = by_id.get(family["loginId"])
        if entry and family_ready(entry, family):
            print(f"{family['loginId']}: already ready", flush=True)
            continue
        try:
            prepare_family(args.base_url, family, entry, save, args.wait, args.host, args.origin)
        except ApiFailure as failure:
            print(f"{family['loginId']}: {failure}", file=sys.stderr)
            break
        finally:
            write()
        print(f"{family['loginId']}: ready ({len(family['children'])} children, COMMUNITY consent, device registered)",
              flush=True)
    ready = sum(1 for f in families if f["loginId"] in by_id and family_ready(by_id[f["loginId"]], f))
    print(f"{ready}/{len(families)} families ready in the secrets file")
    return 0 if ready == len(families) else 1


def outside_repository(path):
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost:5173"))
    parser.add_argument("--count", type=int,
                        help="accounts to have in the secrets file (default 4); with --families the first N families (default all)")
    parser.add_argument("--prefix", default="load", help="login ID prefix; IDs are <prefix><n>, letters and digits only")
    parser.add_argument("--host", help="Host header when the ingress needs one (kind: api.sagomungchi.local)")
    parser.add_argument("--origin", help="Origin header when it differs from --base-url (kind: http://localhost:5173)")
    parser.add_argument("--children", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--grade", type=int, default=5, choices=(3, 4, 5, 6))
    parser.add_argument("--secrets", required=True, type=Path, help="k6 secrets file outside the repository")
    parser.add_argument("--wait", action="store_true", help="wait and retry when the signup IP limit is reached")
    parser.add_argument("--families", type=Path,
                        help="#808 family list JSON (login IDs, names, children); --prefix/--children/--grade are ignored")
    args = parser.parse_args(argv)
    if not args.prefix.isascii() or not args.prefix.isalnum():
        parser.error("--prefix must be letters and digits")
    if not outside_repository(args.secrets):
        parser.error("--secrets must be outside the repository")
    existing = json.loads(args.secrets.read_text(encoding="utf-8")) if args.secrets.exists() else {"accounts": []}
    accounts = existing.get("accounts", [])

    def write():
        args.secrets.parent.mkdir(parents=True, exist_ok=True)
        args.secrets.write_text(json.dumps({**existing, "accounts": accounts}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.families:
        return run_families(args, accounts, write)
    args.count = 4 if args.count is None else args.count
    known = {a.get("loginId") for a in accounts}
    for n in range(1, args.count + 1):
        login_id = f"{args.prefix}{n}".lower()
        if login_id in known:
            continue
        try:
            accounts.append(prepare(args.base_url, login_id, args.children, args.grade, args.wait,
                                    args.host, args.origin))
        except ApiFailure as failure:
            print(f"{login_id}: {failure}", file=sys.stderr)
            break
        finally:
            write()
        print(f"{login_id}: ready ({args.children} children, device registered)", flush=True)
    ready = sum(1 for a in accounts if a.get("loginId"))
    print(f"{ready} ID/password accounts in the secrets file")
    return 0 if ready >= args.count else 1


if __name__ == "__main__":
    sys.exit(main())
