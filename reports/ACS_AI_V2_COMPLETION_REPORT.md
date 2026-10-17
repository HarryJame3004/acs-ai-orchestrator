# BÁO CÁO NGHIỆM THU TOÀN DIỆN: ACS AI V2.1
## Nền Tảng Phát Triển Tự Động & Người Bảo Vệ (Guardian) Độc Lập

**Thời điểm nghiệm thu:** 2026-10-17 22:50 UTC+7  
**Môi trường:** EndeavourOS (Arch Linux rolling) | Kernel: 6.18.55-1-lts | Python: 3.14.8  
**Tình trạng kiểm thử:**
- **ACS Core (`~/autonomous-coding-system`):** 362/362 tests PASS (100%)
- **ACS AI V2 Platform (`~/.local/share/acs-orchestrator`):** 21/21 tests PASS (100%)
- **Tổng cộng:** 383/383 tests PASS (100% không hồi quy)

---

### 1. BẢO VỆ TUYỆT ĐỐI CORELOCK
- **Thư mục bảo vệ:** `/home/khoi/autonomous-coding-system`
- **Chính sách:** READ-ONLY. Zero merges, zero overwrites, zero service restarts.
- **Kết quả xác minh:** Không có bất kỳ thay đổi nào tác động lên mã nguồn ACS Core trong toàn bộ quá trình thi công V2. Tất cả 362 kiểm thử hồi quy của ACS Core hoạt động trơn tru.

---

### 2. MA TRẬN 6 CỔNG KIỂM SOÁT (INTERNAL GATES)

| Cổng | Nội dung triển khai | Trạng thái | Bằng chứng kiểm chứng |
| :--- | :--- | :---: | :--- |
| **Cổng 1** | Khảo sát môi trường, sao lưu baseline và probe CLI an toàn | **VERIFIED** | Bản sao lưu `acs_orchestrator_baseline_20261017_222931.tar.gz` (11.4 MB) với SHA256 checksum; probe `codex` 0.163.0, `agy` 1.4.0, `bwrap` 0.13.0 không tương tác. |
| **Cổng 2** | SQLite WAL Engine, State Machine 14 trạng thái & Persistent Daemon | **VERIFIED** | `db.py` với WAL mode và FTS5; `state_machine.py` với SHA-256 checkpoint; `daemon.py` và `api_server.py` (Port 20129); Systemd unit `acs-ai.service`. (6/6 tests pass) |
| **Cổng 3** | Worker Pool, Git Worktree Isolation & Integration Manager | **VERIFIED** | `worker_adapters.py` (Codex sandbox `--approve-for-me`, AGY Google A, vô hiệu hóa Google B theo Rule 7.3); `worktree_manager.py` với SSD Circuit Breaker 10GB; `scope_and_integration.py` tránh xung đột. (5/5 tests pass) |
| **Cổng 4** | Long-Term Memory (FTS5), MCP Registry & REA Fallback Adapter | **VERIFIED** | `memory.py` phân loại Decision/Failure/Knowledge/Project; `mcp_registry.py` phân quyền vai trò và chặn thoát worktree; `rea_adapter.py` phân tích ELF trong Bubblewrap. (3/3 tests pass) |
| **Cổng 5** | Quality Engine, Evidence Engine, Human Approval & Guardian | **VERIFIED** | `quality.py` ($Q = 0.40T + 0.30S + 0.20M + 0.10E$); `evidence.py` ký HMAC-SHA256 theo commit; `human_approval.py`; `guardian.py` chặn CoreLock và bảo vệ nhánh. (4/4 tests pass) |
| **Cổng 6** | `acsai` TUI (Textual), CLI tương thích ngược & E2E Verification | **VERIFIED** | Giao diện điều khiển TUI 5 tab (`acsai ui`), CLI đa năng `acsai` + `acs-team`, kịch bản E2E kiểm thử khép kín từ nhiệm vụ đến hợp nhất an toàn. (3/3 tests pass) |

---

### 3. ĐẶC TẢ THÀNH PHẦN KỸ THUẬT

#### 3.1 Bể nhân sự (Worker Pool)
1. **`codex-primary` (Hoạt động):** Sử dụng binary `/home/khoi/.npm-global/bin/codex` với cờ `--approve-for-me` (thực thi an toàn trong workspace-write sandbox, từ chối flag `--dangerously-bypass`).
2. **`agy-google-a` (Hoạt động):** Sử dụng binary `/home/khoi/.local/bin/agy` gắn với tài khoản Google trankhoi0606@gmail.com, điều phối non-interactive với timeout.
3. **`agy-google-b` (Vô hiệu hóa an toàn):** Đánh dấu trạng thái `UNVERIFIED` do CLI chưa hỗ trợ đa tài khoản mà không tương tác trực tiếp (tuân thủ nghiêm ngặt Quy tắc 7.3).
4. **`Planner` & `Reviewer` (Hoạt động):** Sử dụng 9Router (`free-coding`, `free-review`) hoàn toàn miễn phí ($0.00).

#### 3.2 Bộ nhớ dài hạn (Long-Term Memory)
- Động cơ SQLite FTS5 toàn diện, phân tách theo dự án.
- Tự động đánh dấu `stale = 1` khi commit mã nguồn dịch chuyển để ngăn mô hình suy diễn trên mã lỗi thời.

#### 3.3 Phân quyền MCP & Cách ly REA
- Ngăn chặn triệt để Path Traversal (chặn `..` hoặc đường dẫn tuyệt đối ra ngoài worktree).
- Phân tích nhị phân an toàn thông qua bwrap sandbox (`--unshare-all`, không cấp mạng, chỉ đọc), tự động trích xuất cờ bảo mật (NX, PIE, RELRO, Stack Canary).

#### 3.4 Người bảo vệ độc lập (Guardian Gatekeeper)
- Bắt buộc kiểm chứng chữ ký số HMAC-SHA256 trên mọi bằng chứng kiểm thử trước khi cho phép hợp nhất.
- Bắt buộc điểm chất lượng $Q \ge 0.85$ và 0 lỗi kiểm thử.
- Veto tuyệt đối đối với mọi hành vi can thiệp vào `/home/khoi/autonomous-coding-system` hoặc các nhánh được bảo vệ (`main`, `master`, `release`).

#### 3.5 Giao diện & Trải nghiệm (TUI & CLI)
- Lệnh mới: `acsai` (mặc định mở TUI Textual 5 tab khi không truyền đối số, hoặc hỗ trợ các lệnh `status`, `daemon`, `worker`, `memory`, `approval`).
- Lệnh cũ: `acs-team` được giữ tương thích 100% với các tùy chọn `status`, `plan`, `run`, `mission`.
