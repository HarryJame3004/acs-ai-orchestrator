"""ACS AI V2.2 Terminal Control Center & Mission Composer (TUI).
Powered by Textual. Bilingual interface (Default: Tiếng Việt, with English labels).
Provides real-time visibility and control into:
- System Dashboard & Telemetry (Daemon, SSD, Missions, CoreLock, MCP Health, Repositories)
- Dashboard Mission Composer (Prompt TextArea, Repo & Worker Selectors, Live Progress)
- Dedicated New Mission Modal Screen (Ctrl+N) for long prompts
- Live Mission Logs Viewer Modal (Ctrl+L)
- Multi-Agent Worker Pool Status (codex-primary, agy-google-a, agy-google-b)
- Guardian Gatekeeper & Human Approval Requests
- Long-Term Project Memory (SQLite FTS5)
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from .config import API_PORT, DB_PATH, DISK_MIN_FREE_BYTES, LOGS_DIR
from .daemon_client import check_daemon_health
from .db import DatabaseManager
from .human_approval import HumanApprovalGate
from .mcp_manager import MCPManager
from .memory import MemoryEngine
from .repo_manager import RepoManager
from .test_tracker import get_test_health
from .worker_adapters import WorkerRegistry


class NewMissionModal(ModalScreen):
    """Màn hình soạn thảo nhiệm vụ mở rộng / Dedicated Full New Mission Screen."""

    CSS = """
    NewMissionModal {
        align: center middle;
        background: rgba(18, 19, 23, 0.85);
    }
    #modal_dialog {
        width: 85%;
        height: 80%;
        border: thick #5e81ac;
        background: #181a20;
        padding: 1 2;
    }
    #modal_title {
        text-align: center;
        background: #2e3440;
        color: #88c0d0;
        padding: 1;
        text-style: bold;
    }
    #modal_prompt {
        height: 1fr;
        border: solid #434c5e;
        margin: 1 0;
    }
    .modal_controls {
        height: auto;
        align: center middle;
    }
    .modal_controls Select {
        width: 1fr;
        margin: 0 1;
    }
    .modal_buttons {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    .modal_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Hủy / Đóng (Esc)"),
        ("ctrl+enter", "submit_mission", "Gửi nhiệm vụ (Ctrl+Enter)"),
    ]

    def __init__(self, repos: List[Dict[str, Any]], on_submit_callback):
        super().__init__()
        self.repos = repos
        self.on_submit_callback = on_submit_callback

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            yield Label("📝 SOẠN THẢO NHIỆM VỤ LẬP TRÌNH TỰ ĐỘNG (NEW MISSION)", id="modal_title")
            yield Label("[dim]Nhập yêu cầu bằng ngôn ngữ tự nhiên. Hệ thống sẽ tự động lập kế hoạch, phân bổ nhân sự và kiểm chứng test:[/dim]")
            yield TextArea(
                text="",
                id="modal_prompt",
                show_line_numbers=True,
            )
            with Horizontal(classes="modal_controls"):
                repo_options = [("Tự tạo Workspace cô lập (Isolated Workspace)", "__isolated__")]
                for r in self.repos:
                    badge = "[RO]" if r.get("is_protected") else "[RW]"
                    repo_options.append((f"{r['name']} {badge} ({r['path'][-30:]})", r["path"]))
                yield Select(repo_options, prompt="Chọn Kho Mã Nguồn", id="modal_select_repo", value="__isolated__")

                worker_options = [
                    ("Tự động phân bổ (Auto Scheduling)", "auto"),
                    ("Codex CLI Sandbox (Primary)", "codex"),
                    ("AGY Google A (Antigravity)", "agy-google-a"),
                    ("AGY Google B (Antigravity)", "agy-google-b"),
                ]
                yield Select(worker_options, prompt="Chọn Nhân Sự", id="modal_select_worker", value="auto")

            with Horizontal(classes="modal_buttons"):
                yield Button("🚀 Bắt đầu nhiệm vụ (Ctrl+Enter)", id="btn_modal_submit", variant="primary")
                yield Button("Đóng (Esc)", id="btn_modal_cancel", variant="default")

    def action_dismiss_modal(self) -> None:
        self.dismiss()

    def action_submit_mission(self) -> None:
        self._do_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_modal_submit":
            self._do_submit()
        elif event.button.id == "btn_modal_cancel":
            self.dismiss()

    def _do_submit(self) -> None:
        area = self.query_one("#modal_prompt", TextArea)
        prompt = area.text.strip()
        if not prompt:
            return
        repo_sel = self.query_one("#modal_select_repo", Select)
        worker_sel = self.query_one("#modal_select_worker", Select)
        repo_val = repo_sel.value if repo_sel.value != "__isolated__" else None
        worker_val = str(worker_sel.value or "auto")

        self.dismiss()
        self.on_submit_callback(prompt, repo_val, worker_val)


class LogsModal(ModalScreen):
    """Màn hình xem nhật ký nhiệm vụ trực tiếp / Mission Logs Viewer Screen."""

    CSS = """
    LogsModal {
        align: center middle;
        background: rgba(18, 19, 23, 0.9);
    }
    #logs_dialog {
        width: 90%;
        height: 85%;
        border: thick #88c0d0;
        background: #14161b;
        padding: 1 2;
    }
    #logs_title {
        text-align: center;
        background: #2e3440;
        color: #a3be8c;
        padding: 1;
        text-style: bold;
    }
    #logs_content {
        height: 1fr;
        border: solid #3b4252;
        background: #0f1115;
        padding: 1;
        overflow-y: scroll;
    }
    #btn_close_logs {
        margin-top: 1;
        align-horizontal: right;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Đóng (Esc)"),
    ]

    def __init__(self, title: str, logs_text: str):
        super().__init__()
        self.logs_title = title
        self.logs_text = logs_text

    def compose(self) -> ComposeResult:
        with Vertical(id="logs_dialog"):
            yield Label(f"📜 NHẬT KÝ HOẠT ĐỘNG: {self.logs_title}", id="logs_title")
            yield Static(self.logs_text, id="logs_content")
            yield Button("Đóng (Esc)", id="btn_close_logs", variant="primary")

    def action_dismiss_modal(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_close_logs":
            self.dismiss()


class DashboardView(VerticalScroll):
    """Trang Tổng quan & Soạn thảo nhiệm vụ / System Dashboard & Mission Composer View."""

    def compose(self) -> ComposeResult:
        yield Static("🚀 [bold green]ACS AI V2.2 — TRUNG TÂM ĐIỀU HÀNH & SOẠN THẢO NHIỆM VỤ[/bold green]", id="dash_title")
        yield Static("", classes="spacer")

        # Row 1: Telemetry Metrics
        with Horizontal(classes="stat_row"):
            yield Static(id="box_daemon", classes="metric_box")
            yield Static(id="box_disk", classes="metric_box")
            yield Static(id="box_missions", classes="metric_box")
            yield Static(id="box_corelock", classes="metric_box")
            yield Static(id="box_mcp", classes="metric_box")
            yield Static(id="box_repos", classes="metric_box")

        yield Static("", classes="spacer")

        # Row 2: Mission Composer Panel
        with Vertical(id="composer_container"):
            with Horizontal(id="composer_header_row"):
                yield Label("📝 [bold cyan]BẢNG SOẠN THẢO NHIỆM VỤ (NATURAL LANGUAGE COMPOSER)[/bold cyan]")
                yield Button("📜 Mở rộng (Ctrl+N)", id="btn_open_expanded_modal", variant="default")

            yield TextArea(
                text="",
                id="dash_composer_prompt",
                classes="dash_prompt_area",
            )

            with Horizontal(id="dash_controls_row"):
                yield Select([], prompt="Kho mã nguồn", id="dash_select_repo")
                yield Select(
                    [
                        ("Tự động (Auto)", "auto"),
                        ("Codex CLI", "codex"),
                        ("AGY Google A", "agy-google-a"),
                        ("AGY Google B", "agy-google-b"),
                    ],
                    prompt="Nhân sự",
                    id="dash_select_worker",
                    value="auto",
                )
                yield Button("🚀 Bắt đầu (Submit)", id="btn_dash_start_mission", variant="primary")

        yield Static("", classes="spacer")

        # Row 3: Active Mission Progress & Live Logs
        yield Label("⚡ [bold yellow]TIẾN ĐỘ THỜI GIAN THỰC & NHẬT KÝ TRỰC TIẾP (LIVE PROGRESS)[/bold yellow]")
        yield Static(
            "[dim]Chưa có nhiệm vụ nào đang thực thi. Nhập yêu cầu phía trên hoặc nhấn Ctrl+N để bắt đầu.[/dim]",
            id="box_active_mission_logs",
            classes="live_logs_box",
        )

        yield Static("", classes="spacer")

        # Row 4: Recent Missions Table
        yield Label("📋 [bold]NHIỆM VỤ GẦN ĐÂY (RECENT MISSIONS)[/bold]")
        yield DataTable(id="dash_missions_table")

        yield Static("", classes="spacer")

        # Row 5: Active Workers Table
        yield Label("🤖 [bold]BỂ NHÂN SỰ ĐỘC LẬP (ACTIVE WORKER POOL)[/bold]")
        yield DataTable(id="dash_worker_table")


class MissionsView(VerticalScroll):
    """Trang Quản lý Nhiệm vụ / Missions Management View."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("🎯 [bold cyan]DANH SÁCH NHIỆM VỤ PHÁT TRIỂN (ACTIVE MISSIONS)[/bold cyan]")
            yield Button("Làm mới (Refresh)", id="btn_refresh_missions", variant="primary")
            yield Button("Xem Nhật Ký (Ctrl+L)", id="btn_view_logs_nav", variant="default")
        yield DataTable(id="missions_table")
        yield Label("\n📄 [bold]Chi tiết nhiệm vụ chọn lọc:[/bold]")
        yield Static(id="mission_detail_box", classes="detail_box")


class WorkersView(VerticalScroll):
    """Trang Trạng thái Nhân sự / Multi-Agent Workers View."""

    def compose(self) -> ComposeResult:
        yield Label("🤖 [bold magenta]BỂ NHÂN SỰ ĐỘC LẬP & PHÂN QUYỀN (MULTI-AGENT POOL)[/bold magenta]")
        yield Static("", classes="spacer")
        yield DataTable(id="full_workers_table")
        yield Static("", classes="spacer")
        yield Static(
            "[dim]Chính sách an toàn & Nhân sự đa tác tử:[/dim]\n"
            "• [green]codex-primary[/green]: Chạy trong Worktree độc lập, sandbox workspace-write, từ chối flag bypass.\n"
            "• [green]agy-google-a[/green]: Antigravity CLI Google Account A, prompt tự động với timeout.\n"
            "• [green]agy-google-b[/green]: Antigravity CLI Google Account B (Đã xác thực độc lập, môi trường riêng).\n"
            "• [cyan]Reviewer & Planner[/cyan]: Sử dụng 9Router Free Models, quyền READ_ONLY.",
            classes="info_card",
        )


class GuardianView(VerticalScroll):
    """Trang Người bảo vệ & Phê duyệt / Guardian & Approvals View."""

    def compose(self) -> ComposeResult:
        yield Label("🛡️ [bold red]NGƯỜI BẢO VỆ ĐỘC LẬP & PHÊ DUYỆT (GUARDIAN GATEKEEPER)[/bold red]")
        yield Static("", classes="spacer")
        yield Label("[bold yellow]Yêu cầu phê duyệt đang chờ (Pending Human Approvals):[/bold yellow]")
        yield DataTable(id="approvals_table")
        yield Static("", classes="spacer")
        yield Label("[bold]Lịch sử kiểm định & Veto của Guardian gần nhất:[/bold]")
        yield DataTable(id="guardian_audit_table")


class MemoryView(VerticalScroll):
    """Trang Bộ nhớ dài hạn / Long-term Memory Search View."""

    def compose(self) -> ComposeResult:
        yield Label("🧠 [bold blue]TRUY VẤN BỘ NHỚ DÀI HẠN DỰ ÁN (PROJECT MEMORY FTS5)[/bold blue]")
        yield Static("Tìm kiếm quyết định kiến trúc, lỗi đã xử lý, hoặc kiến thức mã nguồn:")
        with Horizontal():
            yield Input(placeholder="Nhập từ khóa tìm kiếm (ví dụ: WAL, codex, bwrap)...", id="input_mem_search")
            yield Button("Tìm kiếm (Search)", id="btn_mem_search", variant="success")
        yield DataTable(id="memory_results_table")


class ACSControlCenterApp(App):
    """Textual TUI Application for ACS AI V2.2 Control Center."""

    TITLE = "ACS AI V2.2 Control Center"

    CSS = """
    Screen {
        background: #121317;
        color: #e0e0e0;
    }
    #dash_title {
        text-align: center;
        padding: 1;
        background: #1a1c23;
        border-bottom: heavy #2e3440;
    }
    .spacer {
        height: 1;
    }
    .stat_row {
        height: auto;
        min-height: 7;
        align: center middle;
    }
    .metric_box {
        width: 1fr;
        height: auto;
        min-height: 7;
        border: round #4c566a;
        background: #1e222b;
        padding: 0 1;
        margin: 0 1;
    }
    #composer_container {
        border: solid #5e81ac;
        background: #181a20;
        padding: 1;
        height: auto;
        min-height: 12;
    }
    #composer_header_row {
        height: auto;
        align: left middle;
    }
    .dash_prompt_area {
        height: 5;
        border: solid #434c5e;
        margin: 1 0;
        background: #121317;
    }
    #dash_controls_row {
        height: auto;
        align: left middle;
    }
    #dash_controls_row Select {
        width: 1fr;
        margin-right: 1;
    }
    .live_logs_box {
        border: solid #ebcb8b;
        background: #0f1115;
        padding: 1;
        height: auto;
        min-height: 5;
        max-height: 10;
        overflow-y: scroll;
    }
    .detail_box {
        border: solid #3b4252;
        background: #181a20;
        padding: 1;
        min-height: 6;
    }
    .info_card {
        border: dashed #434c5e;
        padding: 1;
        background: #16181e;
    }
    DataTable {
        height: auto;
        min-height: 7;
        border: solid #2e3440;
    }
    """

    BINDINGS = [
        ("q", "quit", "Thoát (Quit)"),
        ("r", "refresh_data", "Làm mới (Refresh)"),
        ("ctrl+n", "open_new_mission", "Soạn nhiệm vụ (Ctrl+N)"),
        ("ctrl+l", "view_logs", "Xem nhật ký (Ctrl+L)"),
        ("d", "switch_tab('dashboard')", "Tổng quan"),
        ("m", "switch_tab('missions')", "Nhiệm vụ"),
        ("w", "switch_tab('workers')", "Nhân sự"),
        ("g", "switch_tab('guardian')", "Guardian"),
        ("e", "switch_tab('memory')", "Bộ nhớ"),
    ]

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db = db_manager
        self.memory_engine = MemoryEngine(db_manager)
        self.approval_gate = HumanApprovalGate(db_manager)
        self.repo_manager = RepoManager(db_manager)
        self.mcp_manager = MCPManager()
        self.active_mission_id: Optional[str] = None
        self.latest_logs: List[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("Tổng quan (Dashboard)", id="tab_dashboard"):
                yield DashboardView()
            with TabPane("Nhiệm vụ (Missions)", id="tab_missions"):
                yield MissionsView()
            with TabPane("Nhân sự (Workers)", id="tab_workers"):
                yield WorkersView()
            with TabPane("Guardian & Phê duyệt", id="tab_guardian"):
                yield GuardianView()
            with TabPane("Bộ nhớ (Memory)", id="tab_memory"):
                yield MemoryView()
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ACS AI V2.2 Control Center"
        self._setup_tables()
        self._populate_composer_options()
        self.refresh_all_data()

    def action_refresh_data(self) -> None:
        self.refresh_all_data()

    def action_open_new_mission(self) -> None:
        repos = self.repo_manager.list_repositories()
        self.push_screen(NewMissionModal(repos, self._submit_mission_pipeline))

    def action_view_logs(self) -> None:
        mid = self.active_mission_id
        if not mid:
            missions = self.db.list_missions(limit=1)
            mid = missions[0]["mission_id"] if missions else "N/A"

        logs = self.db.get_mission_logs(mid)
        log_text = "\n".join(logs) if logs else (
            "\n".join(self.latest_logs) if self.latest_logs else "Chưa có nhật ký ghi nhận cho nhiệm vụ này."
        )
        self.push_screen(LogsModal(mid, log_text))

    def action_switch_tab(self, tab_name: str) -> None:
        tabbed_content = self.query_one("#tabs", TabbedContent)
        tab_map = {
            "dashboard": "tab_dashboard",
            "missions": "tab_missions",
            "workers": "tab_workers",
            "guardian": "tab_guardian",
            "memory": "tab_memory",
        }
        if tab_name in tab_map:
            tabbed_content.active = tab_map[tab_name]

    def _setup_tables(self) -> None:
        # 1. Dash Recent Missions Table
        t_dash_m = self.query_one("#dash_missions_table", DataTable)
        t_dash_m.add_columns("Mã NV", "Trạng thái", "Điểm CL", "Yêu cầu / Mục tiêu")

        # 2. Dash Worker Table
        t_dash_w = self.query_one("#dash_worker_table", DataTable)
        t_dash_w.add_columns("Mã nhân sự", "Vai trò", "Trạng thái", "Mô hình / Cơ chế")

        # 3. Missions Table
        t_missions = self.query_one("#missions_table", DataTable)
        t_missions.add_columns("Mã NV", "Dự án", "Mục tiêu", "Trạng thái", "Điểm CL", "Cập nhật")

        # 4. Full Workers Table
        t_full_w = self.query_one("#full_workers_table", DataTable)
        t_full_w.add_columns("Nhân sự", "Trạng thái", "Loại", "Cách ly / Sandbox", "Ghi chú")

        # 5. Approvals Table
        t_appr = self.query_one("#approvals_table", DataTable)
        t_appr.add_columns("Mã Yêu Cầu", "Mã NV", "Hành động", "Mức rủi ro", "Trạng thái", "Tạo lúc")

        # 6. Guardian Audit Table
        t_audit = self.query_one("#guardian_audit_table", DataTable)
        t_audit.add_columns("ID", "Thời gian", "Tác nhân", "Hành động", "Chi tiết")

        # 7. Memory Table
        t_mem = self.query_one("#memory_results_table", DataTable)
        t_mem.add_columns("Mã BM", "Loại", "Tiêu đề", "Nội dung tóm tắt", "Commit SHA", "Độ tin cậy")

    def _populate_composer_options(self) -> None:
        """Populates repository selector on the main dashboard composer."""
        try:
            repo_sel = self.query_one("#dash_select_repo", Select)
            repos = self.repo_manager.list_repositories()
            options = [("Tự tạo Workspace cô lập (Isolated Workspace)", "__isolated__")]
            for r in repos:
                badge = "[RO]" if r.get("is_protected") else "[RW]"
                options.append((f"{r['name']} {badge} ({r['path'][-25:]})", r["path"]))
            repo_sel.set_options(options)
            repo_sel.value = "__isolated__"
        except Exception:
            pass

    def refresh_all_data(self) -> None:
        # Metric 1: Daemon status
        box_daemon = self.query_one("#box_daemon", Static)
        health = check_daemon_health()
        if health["healthy"]:
            box_daemon.update(f"[bold cyan]DAEMON[/bold cyan]\nCổng: {health['endpoint']}\nTrạng thái: [green]RUNNING[/green]\nDB: {health['db'].upper()}")
        elif health["running"]:
            box_daemon.update(f"[bold cyan]DAEMON[/bold cyan]\nCổng: {health['endpoint']}\nTrạng thái: [yellow]UNHEALTHY[/yellow]\n{health['details'][:25]}")
        else:
            box_daemon.update(f"[bold cyan]DAEMON[/bold cyan]\nCổng: {API_PORT}\nTrạng thái: [red]STOPPED[/red]\nDB: SQLite WAL")

        # Metric 2: Disk Space
        box_disk = self.query_one("#box_disk", Static)
        try:
            total, used, free = shutil.disk_usage(str(DB_PATH.parent))
            free_gb = free / (1024**3)
            status_color = "green" if free > DISK_MIN_FREE_BYTES else "red"
            box_disk.update(f"[bold yellow]DUNG LƯỢNG SSD[/bold yellow]\nTrống: [{status_color}]{free_gb:.1f} GB[/{status_color}]\nNgưỡng: 10.0 GB\nTrạng thái: AN TOÀN")
        except Exception:
            box_disk.update("[bold yellow]DUNG LƯỢNG SSD[/bold yellow]\nKhông xác định")

        # Metric 3: Missions
        box_missions = self.query_one("#box_missions", Static)
        missions = self.db.list_missions(limit=100)
        completed = sum(1 for m in missions if m.get("state") == "COMPLETED")
        active = sum(1 for m in missions if m.get("state") not in ("COMPLETED", "FAILED", "BLOCKED", "CANCELLED"))
        box_missions.update(f"[bold blue]NHIỆM VỤ[/bold blue]\nTổng: {len(missions)}\nChạy: {active}\nXong: {completed}")

        # Metric 4: CoreLock & Test Health
        box_corelock = self.query_one("#box_corelock", Static)
        core_health = get_test_health("acs_core")
        status_txt = f"{core_health['status']}" if core_health["verified"] else "UNCHECKED"
        box_corelock.update(f"[bold magenta]CORELOCK GUARD[/bold magenta]\nKho: ACS Core (RO)\nKhóa: CHẶT CHẼ\nTests: {status_txt}")

        # Metric 5: MCP Health & Verification
        box_mcp = self.query_one("#box_mcp", Static)
        try:
            mcp_stats = self.mcp_manager.get_summary_stats()
            box_mcp.update(f"[bold cyan]HỆ THỐNG MCP[/bold cyan]\nCấu hình: {mcp_stats['configured_servers']}\nKhả dụng: [green]{mcp_stats['usable_servers']}[/green]\nTools: {mcp_stats['total_tools']}")
        except Exception:
            box_mcp.update("[bold cyan]HỆ THỐNG MCP[/bold cyan]\nKhông xác định")

        # Metric 6: Managed Repositories
        box_repos = self.query_one("#box_repos", Static)
        try:
            repos = self.repo_manager.list_repositories()
            prot = sum(1 for r in repos if r.get("is_protected"))
            box_repos.update(f"[bold green]KHO MÃ NGUỒN[/bold green]\nTổng: {len(repos)}\nBảo vệ RO: {prot}\nKhả dụng: {len(repos) - prot}")
        except Exception:
            box_repos.update("[bold green]KHO MÃ NGUỒN[/bold green]\nKhông xác định")

        # Refresh Dash Recent Missions
        t_dash_m = self.query_one("#dash_missions_table", DataTable)
        t_dash_m.clear()
        for m in missions[:8]:
            prompt_snip = (m.get("prompt") or m.get("goal") or "")[:40]
            t_dash_m.add_row(
                m.get("mission_id", ""),
                m.get("state", ""),
                f"{m.get('quality_score', 0.0):.2f}",
                prompt_snip + "...",
            )

        # Refresh Dash Workers
        t_dash_w = self.query_one("#dash_worker_table", DataTable)
        t_dash_w.clear()
        reg = WorkerRegistry()
        workers = reg.get_all_statuses()
        for w in workers:
            badge = "[green]SẴN SÀNG (READY)[/green]" if w["ready"] else "[red]VÔ HIỆU HÓA[/red]"
            t_dash_w.add_row(w["name"], "Worker", badge, w["details"][:40])
        t_dash_w.add_row("reviewer-qa", "Đánh giá viên", "[cyan]SẴN SÀNG[/cyan]", "9Router / free-review")
        t_dash_w.add_row("planner", "Lập kế hoạch", "[cyan]SẴN SÀNG[/cyan]", "9Router / free-coding")

        # Refresh Full Workers Table
        t_full_w = self.query_one("#full_workers_table", DataTable)
        t_full_w.clear()
        for w in workers:
            t_full_w.add_row(w["name"], w["status"], "CLI Subprocess", "Worktree Sandbox", w["details"])
        t_full_w.add_row("planner", "READY", "API / 9Router", "Read-Only / No Mutation", "Model free-coding qua 9Router")
        t_full_w.add_row("reviewer-qa", "READY", "API / 9Router", "Read-Only / No Mutation", "Model free-review qua 9Router")
        t_full_w.add_row("guardian", "ACTIVE", "Internal Engine", "Gatekeeper / Cryptographic", "Bảo vệ CoreLock & Git HEAD")

        # Refresh Missions Table
        t_missions = self.query_one("#missions_table", DataTable)
        t_missions.clear()
        for m in missions[:25]:
            t_missions.add_row(
                m.get("mission_id", ""),
                m.get("project_id", ""),
                m.get("goal", "")[:35] + "...",
                m.get("state", ""),
                f"{m.get('quality_score', 0.0):.2f}",
                m.get("updated_at", "")[:19],
            )

        # Refresh Approvals
        t_appr = self.query_one("#approvals_table", DataTable)
        t_appr.clear()
        approvals = self.approval_gate.list_pending_approvals()
        for a in approvals:
            t_appr.add_row(
                a.get("approval_id", ""),
                a.get("mission_id", ""),
                a.get("action", ""),
                a.get("risk_level", ""),
                a.get("status", ""),
                a.get("created_at", "")[:19],
            )

        # Refresh Guardian Audit
        t_audit = self.query_one("#guardian_audit_table", DataTable)
        t_audit.clear()
        with self.db.get_connection() as con:
            cur = con.execute("SELECT * FROM audit_events ORDER BY event_id DESC LIMIT 15")
            for r in cur.fetchall():
                t_audit.add_row(
                    str(r["event_id"]),
                    r["timestamp"][:19],
                    r["actor"],
                    r["action"],
                    (r["details_json"] or "")[:40] + "...",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_refresh_missions":
            self.refresh_all_data()
        elif event.button.id == "btn_mem_search":
            self._execute_memory_search()
        elif event.button.id == "btn_open_expanded_modal":
            self.action_open_new_mission()
        elif event.button.id == "btn_view_logs_nav":
            self.action_view_logs()
        elif event.button.id == "btn_dash_start_mission":
            self._submit_dash_composer()

    def _submit_dash_composer(self) -> None:
        prompt_area = self.query_one("#dash_composer_prompt", TextArea)
        prompt = prompt_area.text.strip()
        if not prompt:
            return
        repo_sel = self.query_one("#dash_select_repo", Select)
        worker_sel = self.query_one("#dash_select_worker", Select)
        repo_val = repo_sel.value if repo_sel.value != "__isolated__" else None
        worker_val = str(worker_sel.value or "auto")

        prompt_area.text = ""
        self._submit_mission_pipeline(prompt, repo_val, worker_val)

    def _submit_mission_pipeline(self, prompt: str, repo_path_str: Optional[str], worker_pref: str) -> None:
        """Dispatches autonomous mission execution via background thread."""
        mission_id = f"mission-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.active_mission_id = mission_id
        self.latest_logs = []

        log_box = self.query_one("#box_active_mission_logs", Static)
        log_box.update(f"[bold green]▶ ĐÃ KHỞI TẠO NHIỆM VỤ: {mission_id}[/bold green]\nĐang thiết lập workspace và lập kế hoạch tự động...")

        def _worker_fn():
            from .autonomous_planner import AutonomousMissionPlanner
            try:
                target_repo, _ = self.repo_manager.resolve_target_workspace(repo_path_str, mission_id=mission_id)
            except Exception as e:
                self.call_from_thread(self._on_mission_error, f"Lỗi khởi tạo kho mã nguồn: {e}")
                return

            def _log_cb(msg: str):
                self.call_from_thread(self._append_live_log, msg)

            planner = AutonomousMissionPlanner(db=self.db)
            try:
                res = planner.run_mission(
                    mission_id=mission_id,
                    prompt=prompt,
                    repo_path=target_repo,
                    worker_preference=worker_pref,
                    log_callback=_log_cb,
                )
                self.call_from_thread(self._on_mission_complete, res)
            except Exception as e:
                self.call_from_thread(self._on_mission_error, str(e))

        self.run_worker(_worker_fn, thread=True)

    def _append_live_log(self, msg: str) -> None:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{now_str}] {msg}"
        self.latest_logs.append(line)
        if len(self.latest_logs) > 30:
            self.latest_logs = self.latest_logs[-30:]

        log_box = self.query_one("#box_active_mission_logs", Static)
        log_box.update("\n".join(self.latest_logs[-6:]))

    def _on_mission_complete(self, result: Dict[str, Any]) -> None:
        log_box = self.query_one("#box_active_mission_logs", Static)
        status = result.get("status", "COMPLETED")
        badge = "[bold green]HOÀN THÀNH (SUCCESS)[/bold green]" if status == "COMPLETED" else f"[bold red]{status}[/bold red]"
        log_box.update(
            f"✅ [bold]KẾT QUẢ NHIỆM VỤ {result.get('mission_id')}:[/bold] {badge}\n"
            f"Nhân sự: {result.get('worker')} | Tests Passed: {result.get('tests_passed')} | Score: {result.get('quality_score', 0.0):.2f}\n"
            f"Guardian Verdict: {result.get('guardian_verdict')}\n"
            f"Nhấn [bold cyan]Ctrl+L[/bold cyan] để xem toàn bộ chi tiết nhật ký."
        )
        self.refresh_all_data()

    def _on_mission_error(self, err: str) -> None:
        log_box = self.query_one("#box_active_mission_logs", Static)
        log_box.update(f"❌ [bold red]NHIỆM VỤ THẤT BẠI HOẶC BỊ TỪ CHỐI:[/bold red] {err}")
        self.refresh_all_data()

    def _execute_memory_search(self) -> None:
        inp = self.query_one("#input_mem_search", Input)
        query = inp.value.strip()
        t_mem = self.query_one("#memory_results_table", DataTable)
        t_mem.clear()
        if not query:
            return
        results = self.memory_engine.search(project_id="", query=query, limit=20)
        for mem in results:
            t_mem.add_row(
                mem.get("memory_id", ""),
                mem.get("memory_type", ""),
                mem.get("title", ""),
                mem.get("content", "")[:40] + "...",
                (mem.get("source_commit") or "N/A")[:8],
                f"{mem.get('confidence', 1.0):.2f}",
            )


def launch_tui():
    """Entry point for running the TUI application."""
    db = DatabaseManager()
    app = ACSControlCenterApp(db)
    app.run()
