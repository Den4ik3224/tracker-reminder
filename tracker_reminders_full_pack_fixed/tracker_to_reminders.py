#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Автовыгрузка задач активного спринта доски Яндекс.Трекера в Apple Reminders.
Конфиг из ~/.tracker_reminders.env, запуск строгий: вторник 20:00 МСК.
"""
import os, re, subprocess
from datetime import datetime
from typing import Optional, Any
from zoneinfo import ZoneInfo
from yandex_tracker_client import TrackerClient
from yandex_tracker_client.exceptions import TrackerClientError

ENV_PATH = os.getenv("TRACKER_REMINDERS_ENV") or os.path.expanduser("~/.tracker_reminders.env")


def load_env_file(path: str):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and (k not in os.environ):
                os.environ[k] = v


load_env_file(ENV_PATH)

CLOUD_ORG_ID  = os.getenv("CLOUD_ORG_ID") or ""
YT_BOARD_ID   = os.getenv("YT_BOARD_ID") or ""
YT_QUERY_XTRA = (os.getenv("YT_QUERY_XTRA") or "Status: !Closed").strip()
YT_ASSIGNEE   = os.getenv("YT_ASSIGNEE")
REM_LIST_PREFIX = os.getenv("REM_LIST_PREFIX", "").strip()
if not CLOUD_ORG_ID or not YT_BOARD_ID.isdigit():
    raise SystemExit(f"Set CLOUD_ORG_ID and numeric YT_BOARD_ID in .env ({ENV_PATH}) or env vars.")
BOARD_ID_INT = int(YT_BOARD_ID)


def guard_msk_20():
    now_msk = datetime.now(ZoneInfo("Europe/Moscow"))
    if not (now_msk.hour == 20 and now_msk.minute == 0):
        print("Guard:", now_msk.strftime("%Y-%m-%d %H:%M %Z"), "— not 20:00 MSK; skip.")
        raise SystemExit(0)


def _get_iam_token() -> str:
    tok = os.getenv("IAM_TOKEN")
    if tok:
        return tok.strip()
    try:
        out = subprocess.run(["yc","iam","create-token"], check=True, capture_output=True, text=True).stdout.strip()
        if not out:
            raise RuntimeError("empty token from yc")
        return out
    except Exception as e:
        raise SystemExit(f"Unable to obtain IAM token. Set IAM_TOKEN or install/configure yc. Detail: {e}")


def _quote(s: str) -> str:
    return '"' + s.replace('"','\\"').replace("\\","\\\\").replace("\n"," ").replace("\r"," ") + '"'


def _assignee_clause(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    a = val.strip()
    if not a:
        return None
    low = a.lower()
    if low in {"unassigned","none","empty"}:
        return "Assignee: empty()"
    if a.endswith("()"):
        return f"Assignee: {a}"
    if "," in a:
        parts = []
        for x in [p.strip() for p in a.split(",") if p.strip()]:
            lx = x.lower()
            if lx in {"unassigned","none","empty"}:
                parts.append("Assignee: empty()")
            elif x.endswith("()"):
                parts.append(f"Assignee: {x}")
            else:
                parts.append(f"Assignee: {_quote(x)}")
        return "(" + " or ".join(parts) + ")" if parts else None
    return f"Assignee: {_quote(a)}"


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _extract_email(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        m = EMAIL_RE.search(obj)
        return m.group(0) if m else None
    if isinstance(obj, (list,tuple)):
        for it in obj:
            em = _extract_email(it)
            if em:
                return em
        return None
    if isinstance(obj, dict):
        for k in ("email","display","login","self","name"):
            if k in obj and obj[k]:
                em = _extract_email(obj[k])
                if em:
                    return em
        for v in obj.values():
            em = _extract_email(v)
            if em:
                return em
        return None
    try:
        for k in ("email","display","login","self","name"):
            if hasattr(obj,k):
                em = _extract_email(getattr(obj,k))
                if em:
                    return em
    except Exception:
        pass
    try:
        return _extract_email(str(obj))
    except Exception:
        return None


def build_client() -> TrackerClient:
    return TrackerClient(iam_token=_get_iam_token(), cloud_org_id=CLOUD_ORG_ID)


def get_active_sprint_name_via_sdk(client: TrackerClient, board_id: int) -> Optional[str]:
    board = client.boards[board_id]
    sprints = list(board.sprints.get_all())
    def status_key(s) -> str:
        st = getattr(s,"status",None) or {}
        if isinstance(st,dict):
            return (st.get("key") or st.get("id") or "").lower()
        return (getattr(s,"key","") or getattr(s,"id","")).lower()
    active = [s for s in sprints if status_key(s) in {"inprogress","active","started"}]
    if not active:
        return None
    def sid(s):
        try:
            return int(getattr(s,"id",0) or (s.get("id",0) if isinstance(s,dict) else 0))
        except Exception:
            return 0
    active.sort(key=sid, reverse=True)
    name = getattr(active[0],"name",None) or (active[0].get("name") if isinstance(active[0],dict) else None)
    return name


def active_sprint_query_by_board_id(board_id: int, extra: Optional[str]=None, assignee: Optional[str]=None) -> str:
    parts = [f'"Sprint In Progress By Board": {board_id}']
    a = _assignee_clause(assignee)
    if a:
        parts.append(a)
    if extra and extra.strip():
        parts.append(extra.strip())
    return " and ".join(parts)


def find_issues(client: TrackerClient, q: str):
    return client.issues.find(q, per_page=100)


def add_to_reminders_if_absent(list_name: str, title: str, note: str, due_dt: tuple|None=None):
    esc = lambda s: s.replace('"','\\"')
    set_due = ""
    if due_dt:
        y,m,d,hh,mm = due_dt
        MONTHS=["January","February","March","April","May","June","July","August","September","October","November","December"]
        mon_name = MONTHS[m-1]
        set_due = f"""
            set theDate to (current date)
            set year of theDate to {y}
            set month of theDate to {mon_name}
            set day of theDate to {d}
            set time of theDate to ({hh} * hours + {mm} * minutes)
            set due date of theReminder to theDate
        """
    script = f"""
    set theListName to "{esc(list_name)}"
    set theTitle to "{esc(title)}"
    set theBody to "{esc(note)}"
    tell application "Reminders"
        if not (exists list theListName) then
            make new list with properties {{name:theListName}}
        end if
        tell list theListName
            set theReminder to missing value
            set nameExists to false
            repeat with r in (every reminder)
                if (name of r) is equal to theTitle then
                    set nameExists to true
                    set theReminder to r
                    exit repeat
                end if
            end repeat
            if nameExists is false then
                set theReminder to make new reminder at end with properties {{name:theTitle, body:theBody}}
                {set_due}
            else
                set body of theReminder to theBody
                {set_due}
            end if
        end tell
    end tell
    """
    subprocess.run(["/usr/bin/osascript","-e",script], check=True)


def _parse_deadline_components(issue) -> Optional[tuple]:
    dt_raw = None
    for attr in ("deadline","dueDate"):
        if hasattr(issue,attr):
            dt_raw = getattr(issue,attr)
            if dt_raw:
                break
        try:
            dt_raw = issue.get(attr) if isinstance(issue,dict) else None
            if dt_raw:
                break
        except Exception:
            pass
    if not dt_raw:
        return None
    s = str(dt_raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M","%Y-%m-%d"):
        try:
            from datetime import datetime as _dt
            dt = _dt.strptime(s[:len(fmt)], fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=9, minute=0)
            return (dt.year, dt.month, dt.day, dt.hour, dt.minute)
        except ValueError:
            continue
    return None


def _get_description(issue) -> str:
    desc = ""
    for attr in ("description",):
        if hasattr(issue,attr):
            desc = getattr(issue,attr) or ""
            break
        try:
            desc = issue.get(attr,"")
            if desc:
                break
        except Exception:
            pass
    desc = str(desc).strip().replace("\r"," ")
    return (desc[:2000] + "…") if len(desc) > 2000 else desc


def main():
    guard_msk_20()
    client = build_client()
    sprint_name = get_active_sprint_name_via_sdk(client, BOARD_ID_INT)
    if not sprint_name:
        print("No active sprint by status on the board — nothing to sync.")
        return
    reminders_list = f"{REM_LIST_PREFIX}{sprint_name}" if REM_LIST_PREFIX else sprint_name
    q = active_sprint_query_by_board_id(BOARD_ID_INT, YT_QUERY_XTRA, YT_ASSIGNEE)
    try:
        issues = list(find_issues(client, q))
    except TrackerClientError as e:
        raise SystemExit(f"Tracker query failed: {e}")
    if not issues:
        print("Active sprint has no issues for applied filter — done.")
        return
    added = 0
    for it in issues:
        key = getattr(it,"key","")
        title = f"[{key}] {getattr(it,'summary','')}"
        url = f"https://tracker.yandex.ru/{key}" if key else ""
        assignee_email = _extract_email(getattr(it,"assignee",None)) or "—"
        author_email   = _extract_email(getattr(it,"createdBy",None)) or "—"
        status = getattr(it,"status",None)
        status_disp = status.get("display") if isinstance(status,dict) else ""
        description = _get_description(it)
        deadline_components = _parse_deadline_components(it)
        note_parts = [
            f"Статус: {status_disp}",
            f"Автор: {author_email}",
            f"Исполнитель: {assignee_email}",
            f"Ссылка: {url}",
        ]
        if description:
            note_parts.append("")
            note_parts.append("Описание:")
            note_parts.append(description)
        note = "\n".join(note_parts)
        add_to_reminders_if_absent(reminders_list, title, note, due_dt=deadline_components)
        added += 1
    print(f"Processed {added} issues into Reminders list '{reminders_list}'")


if __name__ == "__main__":
    main()
