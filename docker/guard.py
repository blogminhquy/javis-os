"""Javis update guard: brings the Javis container back when an update leaves it gone or stopped.

Watchtower replaces a container in three steps: stop it, remove it, create the new one. When the stop
or the removal returns an error, it gives up and never creates the new one. The update button gives
Watchtower 10 minutes for the pull AND the removal, and on a VPS with a slow disk deleting the old
container can run past that limit, while Docker still finishes the removal on its own a moment later.
Javis is then simply gone: the domain answers 404 and only a Redeploy brings it back (owner report
2026-11-13).

The guard runs beside Watchtower with the same Docker socket. While Javis runs it keeps a copy of how
that container was created, and it acts only in the states a broken update leaves behind:
  - gone for GRACE seconds: create it again from that copy (on the image its tag points to now,
    which is the new version Watchtower already pulled) and start it;
  - stopped while its image tag already points to a newer image (Watchtower pulled, then the stop
    or the removal failed): start it again, the old version comes back;
  - dead (a removal that broke halfway): remove it and create it again;
  - created by someone else and never started for GRACE seconds: start it.
A container the owner stops by hand still has its tag on its own image, so the guard leaves it alone.

Standard library only and no network: the compose service runs it with network_mode none. The
compose files carry this file inline, where a dollar sign would mean a variable, so it uses none.
Keep docker-compose.yml and docker-compose.hostinger.yml in step with: python tools/sync_guard.py
"""
import http.client
import json
import os
import signal
import socket
import sys
import time
import urllib.parse

NAME = os.environ.get("JAVIS_NAME") or "javis"
SOCKET = os.environ.get("JAVIS_GUARD_SOCKET") or "/var/run/docker.sock"
STORE = os.environ.get("JAVIS_GUARD_DIR") or "/guard"
EVERY = float(os.environ.get("JAVIS_GUARD_EVERY") or 15)
GRACE = float(os.environ.get("JAVIS_GUARD_GRACE") or 120)


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "[guard]", msg, flush=True)


class DockerConnection(http.client.HTTPConnection):
    def __init__(self, timeout):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(SOCKET)
        self.sock = sock


def api(method, path, body=None, timeout=60):
    """(status, decoded JSON or raw text or None) of one Docker Engine API call."""
    conn = DockerConnection(timeout)
    try:
        data = None if body is None else json.dumps(body).encode()
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        resp = conn.getresponse()
        raw = resp.read()
    finally:
        conn.close()
    try:
        return resp.status, json.loads(raw) if raw else None
    except ValueError:
        return resp.status, raw.decode("utf-8", "replace")


def quote(value):
    """For query values. Paths take names and image refs as they are, the way the docker CLI sends them."""
    return urllib.parse.quote(value, safe="")


def tag_image_id(ref):
    """Image ID the tag points to now, None when it is not on this machine."""
    status, body = api("GET", "/images/" + ref + "/json")
    return body.get("Id") if status == 200 and isinstance(body, dict) else None


def endpoint(ep, cid, network):
    """Endpoint settings worth carrying over to a new container (runtime fields dropped)."""
    out = {}
    aliases = [a for a in ep.get("Aliases") or [] if a not in (cid, cid[:12])]
    if aliases and network != "bridge":
        out["Aliases"] = aliases
    for key in ("IPAMConfig", "Links", "DriverOpts"):
        if ep.get(key):
            out[key] = ep[key]
    return out


def create_spec(snap):
    """(create body, extra networks to connect) from a saved inspect, the way Watchtower builds one.

    Values the container only had because its old image set them (Env, Cmd, Labels...) are dropped,
    so the new image's own defaults apply, as they would after a normal update."""
    c, img = snap["container"], snap.get("image") or {}
    cid = c["Id"]
    cfg = json.loads(json.dumps(c["Config"]))
    host = json.loads(json.dumps(c["HostConfig"]))
    for key, empty in (("WorkingDir", ""), ("User", ""), ("Cmd", None), ("Entrypoint", None),
                       ("Healthcheck", None), ("StopSignal", "")):
        if key in cfg and cfg.get(key) == img.get(key):
            cfg[key] = empty
    cfg["Env"] = [e for e in cfg.get("Env") or [] if e not in (img.get("Env") or [])]
    old_labels = img.get("Labels") or {}
    cfg["Labels"] = {k: v for k, v in (cfg.get("Labels") or {}).items() if old_labels.get(k) != v}
    for key in ("Volumes", "ExposedPorts"):
        cfg[key] = {k: v for k, v in (cfg.get(key) or {}).items() if k not in (img.get(key) or {})} or None
    if cfg.get("Hostname") == cid[:12]:
        cfg["Hostname"] = ""
    cfg.pop("MacAddress", None)
    # Anonymous volumes live only in the inspect's Mounts; name them so their data comes back too.
    taken = {m.get("Target") for m in host.get("Mounts") or []}
    taken |= {b.split(":")[1] for b in host.get("Binds") or [] if ":" in b}
    for m in c.get("Mounts") or []:
        if m.get("Type") == "volume" and m.get("Name") and m.get("Destination") not in taken:
            bind = m["Name"] + ":" + m["Destination"] + ("" if m.get("RW", True) else ":ro")
            host["Binds"] = (host.get("Binds") or []) + [bind]
    networks = (c.get("NetworkSettings") or {}).get("Networks") or {}
    mode = host.get("NetworkMode") or ""
    extra = {}
    cfg["HostConfig"] = host
    if mode in ("host", "none") or mode.startswith("container:") or not networks:
        return cfg, extra
    primary = mode if mode in networks else next(iter(networks))
    cfg["NetworkingConfig"] = {"EndpointsConfig": {primary: endpoint(networks[primary], cid, primary)}}
    for net, ep in networks.items():
        if net != primary:
            extra[net] = endpoint(ep, cid, net)
    return cfg, extra


def pull(ref):
    image, _, tag = ref.rpartition(":")
    if not image or "/" in tag or "@" in ref:
        image, tag = ref, ""
    query = "fromImage=" + quote(image) + ("&tag=" + quote(tag) if tag else "")
    status, _ = api("POST", "/images/create?" + query, timeout=1800)
    log("pull " + ref + ": HTTP " + str(status))


def create(snap, body):
    """POST /containers/create. Compose notes the image ID in a label; it is pointed at the image the
    tag names now, as Watchtower does, so the next `docker compose up` does not recreate it for nothing."""
    new_image = tag_image_id(body.get("Image") or "")
    if new_image and body["Labels"].get("com.docker.compose.image") == snap["container"].get("Image"):
        body["Labels"]["com.docker.compose.image"] = new_image
    return api("POST", "/containers/create?name=" + quote(NAME), body, timeout=300)


def recreate(snap):
    """Create and start the container from the snapshot. True when it is running again."""
    body, extra = create_spec(snap)
    status, resp = create(snap, body)
    if status == 404:   # the image is not on this machine any more: fetch it, then try once more
        pull(body.get("Image") or "")
        status, resp = create(snap, body)
    if status == 409:
        log("the name " + NAME + " is taken again (Watchtower may have made it meanwhile): leaving it")
        return False
    if status != 201:
        log("create failed: HTTP " + str(status) + " " + str(resp))
        return False
    new_id = resp["Id"]
    for net, ep in extra.items():
        s, r = api("POST", "/networks/" + net + "/connect", {"Container": new_id, "EndpointConfig": ep})
        if s != 200:
            log("connect to network " + net + " failed: HTTP " + str(s) + " " + str(r))
    return start(new_id)


def start(ref):
    status, resp = api("POST", "/containers/" + ref + "/start", timeout=300)
    if status in (204, 304):
        log("started " + NAME)
        return True
    log("start failed: HTTP " + str(status) + " " + str(resp))
    return False


def snapshot_path():
    return os.path.join(STORE, NAME + ".json")


def load_snapshot():
    try:
        with open(snapshot_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_snapshot(snap):
    try:
        os.makedirs(STORE, exist_ok=True)
        tmp = snapshot_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        os.replace(tmp, snapshot_path())
    except OSError as e:
        log("could not save the snapshot (kept in memory only): " + str(e))


class Guard:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.snap = load_snapshot()   # {"container": inspect, "image": its image's Config, "owner_stopped": ID}
        self.since = None             # when the current problem was first seen

    def check(self):
        status, c = api("GET", "/containers/" + NAME + "/json")
        if status == 404:
            return self.missing()
        if status != 200 or not isinstance(c, dict):
            return "unknown"
        state = (c.get("State") or {}).get("Status") or ""
        if state in ("running", "restarting", "paused", "removing"):
            self.since = None
            snap = self.snap or {}
            if state == "running" and (snap.get("container", {}).get("Id") != c["Id"] or snap.get("owner_stopped")):
                s, img = api("GET", "/images/" + c["Image"] + "/json")
                self.snap = {"container": c, "image": (img or {}).get("Config") if s == 200 else None}
                save_snapshot(self.snap)
                log("watching " + NAME + " (" + c["Id"][:12] + ")")
            return "ok"
        return self.not_running(c, state)

    def waited(self):
        """True once the same problem has lasted GRACE seconds."""
        if self.since is None:
            self.since = self.now()
        return self.now() - self.since >= GRACE

    def missing(self):
        if not self.snap or not self.waited():
            return "waiting" if self.snap else "no-snapshot"
        log(NAME + " has been gone for " + str(int(GRACE)) + "s (an update stopped halfway?): creating it again")
        self.since = None
        return "recreated" if recreate(self.snap) else "failed"

    def not_running(self, c, state):
        if c["Id"] == (self.snap or {}).get("owner_stopped"):
            return "owner-stopped"
        seen = (self.snap or {}).get("container", {}).get("Id")
        if state == "dead":
            if not self.snap or not self.waited():
                return "waiting"
            log(NAME + " is dead (a removal broke halfway): removing it and creating it again")
            api("DELETE", "/containers/" + c["Id"] + "?force=1", timeout=300)
            self.since = None
            return "recreated" if recreate(self.snap) else "failed"
        if c["Id"] == seen and state == "exited":
            ref = (c.get("Config") or {}).get("Image") or ""
            if self.since is None and tag_image_id(ref) == c.get("Image"):
                self.snap["owner_stopped"] = c["Id"]   # kept on disk: a restarted guard leaves it alone too
                save_snapshot(self.snap)
                return "owner-stopped"
            if not self.waited():
                return "waiting"
            log(NAME + " was stopped by an update that never finished: starting it again")
        elif state == "created" and c["Id"] != seen:
            if not self.waited():
                return "waiting"
            log(NAME + " was created but never started: starting it")
        else:
            return "left-alone"
        self.since = None
        return "started" if start(c["Id"]) else "failed"


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    log("guarding container " + NAME + " (checks every " + str(int(EVERY)) + "s, acts after " + str(int(GRACE)) + "s)")
    guard = Guard()
    while True:
        try:
            guard.check()
        except Exception as e:  # the Docker socket can be busy or briefly gone: try again next round
            log("check failed: " + type(e).__name__ + ": " + str(e))
        time.sleep(EVERY)


if __name__ == "__main__":
    main()
