"""MCP bridge from Codex to Gemini in the Antigravity SDK runtime."""
from __future__ import annotations
import asyncio
import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import webbrowser
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import common
import dashboard
import progress

JOBS: dict[str, dict] = {}
PANEL: dashboard.PanelServer | None = None
DEFAULT_PROJECT_DIR = ""
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
NETWORK_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def stop_process(process):
    if process is None or process.returncode is not None:
        return
    if os.name == "nt":
        # Terminate the worker and the SDK's child harness together.
        killer = await asyncio.create_subprocess_exec(
            "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await killer.wait()
    else:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 10)
    except TimeoutError:
        process.kill()
        await process.wait()


@asynccontextmanager
async def lifespan(_server):
    try:
        yield {}
    finally:
        tasks = [job["future"] for job in JOBS.values() if not job["future"].done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        global PANEL
        if PANEL is not None:
            await asyncio.to_thread(PANEL.close)
            PANEL = None


mcp = FastMCP("gemini-antigravity", lifespan=lifespan,
              instructions="Delegate tasks to the user's selected relay Gemini model using Antigravity SDK. "
              "Use get_configuration first. Use submit_task with an absolute project directory, then get_job. "
              "Use get_panel for the unified connection and task UI. Open its URL, or submit_task's dashboard_url, "
              "in a Codex right browser panel with open_in_codex when that app tool is available. "
              "Review mode is read-only. Use edit mode only for a task that authorizes changes and commands. "
              "Never request the API key in chat; the user enters it in the local configuration window.")


@mcp.tool(annotations=READ)
def get_configuration() -> dict:
    """Read the selected model and readiness. Never returns an API key."""
    settings = common.load_settings()
    return {**settings, "key_configured": common.has_key(), "ready": common.has_key() and bool(settings["model"]) and bool(settings["base_url"]),
            "runtime": "Antigravity SDK", "configuration_launcher": str(common.APP_DIR / "configure.cmd"),
            "note": "The relay model's native Gemini/tool-call compatibility must be tested with your key."}


def ensure_panel() -> dashboard.PanelServer:
    global PANEL
    if PANEL is None:
        PANEL = dashboard.PanelServer(panel_dispatch, asyncio.get_running_loop()).start()
        common._atomic_write(common.STATE_DIR / "panel.json", json.dumps({"url": PANEL.url}).encode("utf-8"))
    return PANEL


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def get_panel(project_dir: str = "") -> dict:
    """Get the unified local UI for connection setup, model selection, tasks and live progress.

    Open url with open_in_codex, target type browser, placement right. No key is returned.
    project_dir optionally prefills an existing absolute project directory in the task form.
    """
    global DEFAULT_PROJECT_DIR
    if project_dir:
        project = Path(project_dir)
        if not project.is_absolute() or not project.is_dir():
            raise common.RelayError("project_dir 必须是存在的绝对路径。")
        DEFAULT_PROJECT_DIR = str(project.resolve())
    return {"url": ensure_panel().url, "placement": "right", "runtime": "Antigravity SDK"}


def panel_credentials(payload: dict) -> tuple[str, str, str]:
    base = common.normalize_base(str(payload.get("base_url", "")))
    entered = str(payload.get("key", "")).strip()
    if len(entered) > 8192:
        raise common.RelayError("API Key 长度超出范围。")
    if not entered and base != common.load_settings()["base_url"]:
        raise common.RelayError("修改中转站地址时，请重新填写该站的 API Key。")
    return base, entered or common.load_key(), entered


async def panel_dispatch(method: str, action: str, payload: dict) -> dict:
    if method == "GET":
        if action == "jobs":
            return {"jobs": await asyncio.to_thread(progress.list_jobs), "updated_at": now()}
        if action == "config":
            config = get_configuration()
            return {key: config[key] for key in ("base_url", "model", "key_configured", "ready", "runtime")} | {
                "default_project_dir": DEFAULT_PROJECT_DIR}
    if action in ("config", "models", "test"):
        key = ""
        try:
            base, key, entered = panel_credentials(payload)
            if action == "models":
                models = await asyncio.to_thread(common.fetch_models, base, key)
                return {"models": models, "total_count": len(models), "selected": common.load_settings()["model"]}
            model = str(payload.get("model", "")).strip()
            if not model or len(model) > 512:
                raise common.RelayError("请先选择有效的模型。")
            if action == "test":
                reply = await asyncio.to_thread(common.test_native_model, base, key, model)
                return {"ok": True, "reply": common.redact(reply, key)}
            if entered:
                common.save_key(entered)
            common.save_settings(base, model)
            return {"ok": True, **await panel_dispatch("GET", "config", {})}
        except Exception as exc:
            raise common.RelayError(common.redact(str(exc), key, str(payload.get("key", "")))) from None
    if action == "tasks":
        mode = payload.get("mode", "review")
        if mode not in ("review", "edit"):
            raise common.RelayError("任务模式必须为 review 或 edit。")
        timeout = payload.get("timeout_seconds", 600)
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise common.RelayError("超时必须是整数秒。")
        task, project = payload.get("task"), payload.get("project_dir")
        if not isinstance(task, str) or not isinstance(project, str):
            raise common.RelayError("请填写任务和项目目录。")
        return await submit_task(task, project, mode=mode, timeout_seconds=timeout)
    if action == "cancel":
        return await cancel_job(str(payload.get("job_id", "")))
    raise common.RelayError("接口不存在。")


@mcp.tool(annotations=NETWORK_READ)
async def list_models(query: str = "gemini") -> dict:
    """Fetch available model IDs from the relay. Empty query returns every model."""
    settings = common.load_settings()
    models = await asyncio.to_thread(common.fetch_models, settings["base_url"], common.load_key())
    matches = [model for model in models if query.casefold() in model.casefold()]
    return {"models": matches, "matched_count": len(matches), "total_count": len(models), "selected": settings["model"]}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def select_model(model: str) -> dict:
    """Save an exact model ID from the relay list, only when the user asks to change their selection."""
    settings = common.load_settings()
    models = await asyncio.to_thread(common.fetch_models, settings["base_url"], common.load_key())
    if model not in models:
        raise common.RelayError("模型不在当前 Key 可访问的模型列表中，请先调用 list_models。")
    common.save_settings(settings["base_url"], model)
    return {"selected": model}


@mcp.tool(annotations=NETWORK_READ)
async def test_connection() -> dict:
    """Send one small generateContent request to test the saved model's native Gemini endpoint (uses relay quota)."""
    settings = common.load_settings()
    if not settings["model"]:
        raise common.RelayError("请先在配置窗口选择并保存模型。")
    result = await asyncio.to_thread(common.test_native_model, settings["base_url"], common.load_key(), settings["model"])
    return {"ok": True, "model": settings["model"], "reply": result,
            "note": "Basic generation passed; a delegated task additionally checks SDK and tool-call compatibility."}


async def execute(job: dict, task: str, timeout_seconds: int):
    process = None
    key = ""
    try:
        key = common.load_key()
        run_dir = common.STATE_DIR / "jobs" / job["job_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                       "GEMINI_RELAY_STATE_DIR": str(common.STATE_DIR.resolve())}
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(common.APP_DIR / "agent_runner.py"), "--project", job["project_dir"],
            "--mode", job["mode"], "--model", job["model"], "--run-dir", str(run_dir.resolve()),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=environment, cwd=job["project_dir"], **options,
        )
        job["process"] = process
        async with asyncio.timeout(timeout_seconds):
            stdout, stderr = await process.communicate(json.dumps({"task": task}, ensure_ascii=False).encode("utf-8"))
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            detail = stderr.decode("utf-8", "replace")[-2500:]
            raise common.RelayError("代理运行程序未正常返回 JSON。" + common.redact(detail, key)) from None
        if process.returncode != 0 or not result.get("ok"):
            raise common.RelayError(result.get("error", "代理运行程序失败。"))
        if not str(result.get("text", "")).strip():
            raise common.RelayError("代理没有返回可见结果，任务未确认完成。请查看活动记录，或缩小任务后重试。")
        job.update(status="completed", result=common.redact(result.get("text", ""), key))
    except asyncio.CancelledError:
        await stop_process(process)
        job.update(status="cancelled")
    except TimeoutError:
        await stop_process(process)
        job.update(status="timed_out", error=f"任务超过 {timeout_seconds} 秒，已停止。")
    except Exception as exc:
        await stop_process(process)
        job.update(status="failed", error=common.redact(str(exc), key))
    finally:
        job["finished_at"] = now()
        progress.save_job(job)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def submit_task(task: str, project_dir: str, mode: Literal["review", "edit"] = "review",
                      model: str | None = None, timeout_seconds: int = 600) -> dict:
    """Delegate a bounded task to Gemini in Antigravity. Returns a job ID immediately.

    Review enables only file reading/search. Edit additionally permits project file changes
    and shell commands; use it only when the assigned task authorizes those actions.
    project_dir must be an existing absolute path. Poll get_job for results.
    """
    if not task.strip() or len(task) > 100000:
        raise common.RelayError("任务不能为空。")
    project = Path(project_dir)
    if not project.is_absolute() or not project.is_dir():
        raise common.RelayError("project_dir 必须是存在的绝对路径。")
    if not 10 <= timeout_seconds <= 1800:
        raise common.RelayError("timeout_seconds 必须在 10 到 1800 秒之间。")
    settings = common.load_settings()
    key = common.load_key()
    selected = model or settings["model"]
    if not selected:
        raise common.RelayError("请先选择模型。")
    if sum(job["status"] == "running" for job in JOBS.values()) >= 2:
        raise common.RelayError("已有两个任务运行中，请等待完成或取消其中一个。")
    # Bound in-memory history; active jobs are never discarded.
    if len(JOBS) >= 50:
        for job_id, old in list(JOBS.items()):
            if old["status"] != "running":
                del JOBS[job_id]
                if len(JOBS) < 50:
                    break
    job_id = uuid.uuid4().hex[:16]
    panel = ensure_panel()
    job = {"job_id": job_id, "status": "running", "model": selected, "mode": mode,
           "project_dir": str(project.resolve()), "started_at": now(),
           "title": common.redact(task.strip().splitlines()[0], key)[:100],
           "_pid": os.getpid(), "_control_url": panel.url}
    JOBS[job_id] = job
    progress.save_job(job)
    job["future"] = asyncio.create_task(execute(job, task, timeout_seconds))
    return {key: value for key, value in job.items() if key != "future" and not key.startswith("_")} | {
        "dashboard_url": panel.url}


@mcp.tool(annotations=READ)
async def get_job(job_id: str, wait_seconds: int = 0, offset: int = 0, max_chars: int = 20000) -> dict:
    """Read a delegated task's status/result. Optionally wait up to 20 seconds. Results support pagination."""
    job = JOBS.get(job_id) or progress.load_job(job_id)
    if job is None:
        raise common.RelayError("任务不存在。")
    if not 0 <= wait_seconds <= 20 or offset < 0 or not 100 <= max_chars <= 50000:
        raise common.RelayError("查询参数超出范围。")
    if wait_seconds and job["status"] == "running" and "future" in job:
        await asyncio.wait({job["future"]}, timeout=wait_seconds)
    result = {key: value for key, value in job.items() if key not in ("future", "process", "result") and not key.startswith("_")}
    activity = progress.snapshot(job, include_result=False)
    result.update(status=activity["status"], progress=activity["progress"])
    if "result" in job:
        full = job["result"]
        result.update(result=full[offset:offset + max_chars], offset=offset, total_chars=len(full),
                      next_offset=offset + max_chars if offset + max_chars < len(full) else None)
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def cancel_job(job_id: str) -> dict:
    """Cancel a delegated job and terminate its local worker and Antigravity child process."""
    if job_id not in JOBS:
        saved = progress.load_job(job_id)
        if saved is None:
            raise common.RelayError("任务不存在。")
        if saved.get("status") != "running":
            return {"job_id": job_id, "status": saved["status"]}
        if not progress.process_alive(saved.get("_pid", 0)):
            saved.update(status="interrupted", finished_at=now())
            progress.save_job(saved)
            return {"job_id": job_id, "status": "interrupted"}
        owner = saved.get("_control_url", "")
        if not owner or PANEL is not None and owner == PANEL.url:
            raise common.RelayError("任务不属于当前运行服务，无法取消。")
        try:
            return await asyncio.to_thread(dashboard.local_request, owner + "api/cancel", {"job_id": job_id}, timeout=20)
        except Exception:
            raise common.RelayError("无法连接任务所属服务，请稍后重试。") from None
    job = JOBS[job_id]
    if job["status"] == "running":
        job["future"].cancel()
        await asyncio.gather(job["future"], return_exceptions=True)
        # A task cancelled before its coroutine started has no finally block.
        if job["status"] == "running":
            job.update(status="cancelled", finished_at=now())
        progress.save_job(job)
    return {"job_id": job_id, "status": job["status"]}


async def run_panel(project_dir: str = "", open_browser: bool = True):
    existing = await asyncio.to_thread(dashboard.existing_panel)
    if existing:
        if open_browser:
            webbrowser.open(existing)
        elif sys.stdout is not None:
            print(json.dumps({"url": existing}), flush=True)
        return
    async with lifespan(mcp):
        info = await get_panel(project_dir)
        if open_browser:
            webbrowser.open(info["url"])
        elif sys.stdout is not None:
            print(json.dumps(info), flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", action="store_true", help="Run the unified web panel")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--project-dir", default="")
    args = parser.parse_args()
    if args.panel:
        asyncio.run(run_panel(args.project_dir, not args.no_browser))
    else:
        mcp.run(transport="stdio")
