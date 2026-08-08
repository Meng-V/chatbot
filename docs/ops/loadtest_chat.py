"""REAL load test: N simultaneous students, each holding a socket and asking
real questions through the full chat path.

Unlike the earlier /health/live test -- which only proved the HTTP stack could
accept connections -- this drives the whole thing: socket handshake, message
validation, rate limiter, kNN classifier (a real embedding call), the
short-circuit table or the agent+synthesizer, LibCal, the post-processor, and
the reply back down the socket.

WHAT IT COSTS
Roughly half the questions are hours/greeting shaped, which the deterministic
short-circuits answer with no model call at all. The rest go through the model.
At the measured $0.0041 average that is well under a dollar for a full ramp.
Spend lands on the DEVELOPMENT purse: no Origin header is sent, so
_looks_like_dev_client() tags the socket v2_turn_dev.

SAFETY
  * aborts if free memory drops below MEM_FLOOR_MB (this box is 4GB and lost a
    freshly built index to an OOM on 2026-07-29)
  * aborts if the service cgroup passes SVC_CEILING_MB (systemd MemoryMax 2500M)
  * per-question timeout, so a hung turn is recorded rather than hanging the run
  * no room-booking questions -- those consume a real quota

Usage:  python loadtest_chat.py [--max 80] [--questions 2]
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import socketio

BASE = "http://127.0.0.1:8081"
PATH = "/smartchatbot/socket.io"
MEM_FLOOR_MB = 400
SVC_CEILING_MB = 2200
ANSWER_TIMEOUT_S = 90

# Half of these are answered by a deterministic rule (no model call), which
# mirrors the 54% measured on the gold set. The rest exercise retrieval and
# the synthesizer.
FREE_Q = [
    "is the library open right now",
    "what time does King close today",
    "are you open on Saturday",
    "hello",
    "what are Wertz hours",
]
PAID_Q = [
    "do you lend chargers",
    "where is the quiet study area",
    "how do I request an interlibrary loan",
    "who is my subject librarian for chemistry",
    "how long can I keep a book",
]


def avail_mb() -> int:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 99999


def svc_mb() -> int:
    try:
        with open("/sys/fs/cgroup/system.slice/chatbot.service/memory.current") as f:
            return int(f.read().strip()) // 1048576
    except Exception:
        return -1


async def one_student(idx: int, n_questions: int, out: list) -> None:
    """One student: connect, ask, wait for each answer, disconnect."""
    sio = socketio.AsyncClient(reconnection=False)
    answers: asyncio.Queue = asyncio.Queue()

    @sio.on("message")
    async def _on_message(data):  # noqa: ANN001
        await answers.put(data)

    t_conn = time.perf_counter()
    try:
        await asyncio.wait_for(
            sio.connect(BASE, socketio_path=PATH, transports=["websocket"]),
            timeout=30)
    except Exception as e:  # noqa: BLE001
        out.append(("connect_fail", type(e).__name__, 0.0))
        return
    conn_ms = (time.perf_counter() - t_conn) * 1000
    out.append(("connect_ok", "", conn_ms))

    try:
        for q in range(n_questions):
            pool = FREE_Q if (idx + q) % 2 == 0 else PAID_Q
            msg = pool[(idx + q) % len(pool)]
            while not answers.empty():
                answers.get_nowait()
            t0 = time.perf_counter()
            try:
                await sio.emit("message", msg)
                await asyncio.wait_for(answers.get(), timeout=ANSWER_TIMEOUT_S)
                out.append(("answer_ok", "", (time.perf_counter() - t0) * 1000))
            except asyncio.TimeoutError:
                out.append(("answer_timeout", msg[:24],
                            (time.perf_counter() - t0) * 1000))
            except Exception as e:  # noqa: BLE001
                out.append(("answer_error", type(e).__name__,
                            (time.perf_counter() - t0) * 1000))
    finally:
        try:
            await sio.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def level(n: int, n_questions: int) -> dict:
    out: list = []
    t0 = time.perf_counter()
    await asyncio.gather(*(one_student(i, n_questions, out) for i in range(n)))
    dur = time.perf_counter() - t0
    kinds: dict = {}
    for k, _d, _ms in out:
        kinds[k] = kinds.get(k, 0) + 1
    lat = sorted(ms for k, _d, ms in out if k == "answer_ok")
    return {
        "students": n, "wall_s": dur, "kinds": kinds, "lat": lat,
        "detail": [(k, d) for k, d, _ in out if k not in ("connect_ok", "answer_ok")],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=80)
    ap.add_argument("--questions", type=int, default=2)
    args = ap.parse_args()

    ladder = [n for n in (1, 3, 5, 10, 20, 40, 80) if n <= args.max]
    print(f"{'students':>8} {'asked':>6} {'ok':>5} {'timeout':>8} {'err':>5} "
          f"{'p50s':>7} {'p95s':>7} {'max s':>7} {'wall s':>7} {'avail':>6} {'svc':>6}")
    print("-" * 96)
    for n in ladder:
        a = avail_mb()
        if a < MEM_FLOOR_MB:
            print(f"ABORT: only {a}MB free (floor {MEM_FLOOR_MB})")
            break
        if svc_mb() > SVC_CEILING_MB:
            print(f"ABORT: service at {svc_mb()}MB (ceiling {SVC_CEILING_MB})")
            break
        r = await level(n, args.questions)
        k = r["kinds"]
        lat = r["lat"]
        asked = n * args.questions
        p50 = statistics.median(lat) / 1000 if lat else 0
        p95 = (sorted(lat)[max(0, int(len(lat) * .95) - 1)] / 1000) if lat else 0
        mx = (max(lat) / 1000) if lat else 0
        print(f"{n:>8} {asked:>6} {k.get('answer_ok', 0):>5} "
              f"{k.get('answer_timeout', 0):>8} "
              f"{k.get('answer_error', 0) + k.get('connect_fail', 0):>5} "
              f"{p50:>7.2f} {p95:>7.2f} {mx:>7.2f} {r['wall_s']:>7.1f} "
              f"{avail_mb():>6} {svc_mb():>6}")
        for kind, d in r["detail"][:3]:
            print(f"          !! {kind}: {d}")
        await asyncio.sleep(5)   # let the box settle between levels


if __name__ == "__main__":
    asyncio.run(main())
