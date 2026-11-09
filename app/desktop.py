"""Native Windows desktop window for Mini Cursor."""
import argparse
import io
import json
import os
from pathlib import Path
import queue
import runpy
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from tkinter import filedialog, messagebox, simpledialog, ttk

from agent_core import Agent, DEFAULT_MODEL, PROMPT_KEY_NOTICE, demo_fixture, remove_prompt_keys
from agent_tools import read_file
from demo_mcp import pipe, serve as serve_demo_mcp
from durable import daemon_enabled, run_workflow
from shell_runner import Cancelled
from skills_runtime import SCRIPTS, skill_script_path

BG = "#10151f"
PANEL = "#18212e"
TEXT = "#e4ebf5"
MUTED = "#a2b4cc"
ACCENT = "#63d5cb"
ERROR = "#ff8f9a"
HIDDEN_NAMES = {".git", ".venv", "__pycache__", "build", "dist", "release", ".env", ".mini-cursor"}


class Desktop:
    def __init__(self, root, workspace=None):
        self.root = root
        self.workspace = Path(workspace).resolve() if workspace else None
        self.key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = DEFAULT_MODEL
        self.history = []
        self.cancel = None
        self.events = queue.Queue()
        self.preview_path = None
        self.preview_offset = 1
        self.config = None
        self.allow_shell = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="就绪")
        self.location = tk.StringVar(value="请选择工作区")
        self.configure()
        self.layout()
        self.refresh_files()
        root.after(65, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def configure(self):
        self.root.title("Mini Cursor | 桌面编程智能体")
        self.root.geometry("1240x780")
        self.root.minsize(970, 600)
        self.root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 19, "bold"), foreground=ACCENT)
        style.configure("Hint.TLabel", foreground=MUTED)
        style.configure("TButton", padding=(9, 6))
        style.configure("Accent.TButton", foreground="#102724", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#8ce9e1")])
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.configure("Treeview", fieldbackground=PANEL, background=PANEL,
                        foreground=TEXT, rowheight=26)
        style.map("Treeview", background=[("selected", "#275365")])

    def layout(self):
        header = ttk.Frame(self.root, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Mini Cursor", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.location, style="Hint.TLabel").pack(side="left", padx=15)
        controls = [
            ("选择工作区", self.choose_workspace), ("API 设置", self.settings),
            ("MCP 配置", self.choose_mcp), ("离线演示", self.demo),
        ]
        if daemon_enabled():
            controls.append(("续跑检查", self.start_durable))
        for caption, action in reversed(controls):
            ttk.Button(header, text=caption, command=action).pack(side="right", padx=(5, 0))

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=13)
        files = ttk.Frame(body, padding=(0, 0, 6, 0))
        code = ttk.Frame(body, padding=(6, 0))
        activity = ttk.Frame(body, padding=(6, 0, 0, 0))
        for pane, weight in [(files, 1), (code, 2), (activity, 2)]:
            body.add(pane, weight=weight)

        ttk.Label(files, text="文件").pack(anchor="w", pady=(0, 6))
        self.tree = ttk.Treeview(files, show="tree", selectmode="browse")
        self.tree.column("#0", width=205, minwidth=150)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_file)
        self.tree.bind("<<TreeviewOpen>>", self.expand_folder)
        ttk.Button(files, text="刷新文件", command=self.refresh_files).pack(fill="x", pady=6)

        code_header = ttk.Frame(code)
        code_header.pack(fill="x", pady=(0, 6))
        self.code_title = ttk.Label(code_header, text="代码预览")
        self.code_title.pack(side="left")
        ttk.Button(code_header, text="下一页", command=self.next_page).pack(side="right")
        self.code = self.text_panel(code, ("Consolas", 10))
        self.show_code("在左侧选择文本文件。")

        ttk.Label(activity, text="对话与工具调用").pack(anchor="w", pady=(0, 6))
        self.log = self.text_panel(activity, ("Microsoft YaHei UI", 10))
        for tag, color in [("call", ACCENT), ("error", ERROR), ("diff", "#f3cf82"),
                           ("mcp", "#adacff"), ("skill", "#93e5b9"), ("status", MUTED), ("answer", TEXT)]:
            self.log.tag_configure(tag, foreground=color)
        ttk.Label(activity, text="任务输入 · API Key 在上方「API 设置」填写",
                  style="Hint.TLabel").pack(anchor="w", pady=(5, 0))
        self.prompt = tk.Text(activity, height=3, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=("Microsoft YaHei UI", 10), padx=9, pady=6)
        self.prompt.pack(fill="x", pady=(7, 3))
        self.prompt.bind("<Control-Return>", lambda event: (self.send(), "break")[1])
        actions = ttk.Frame(activity)
        actions.pack(fill="x", pady=(0, 6))
        self.shell_check = ttk.Checkbutton(actions, text="允许终端命令", variable=self.allow_shell)
        self.shell_check.pack(side="left")
        self.send_button = ttk.Button(actions, text="发送", style="Accent.TButton", command=self.send)
        self.send_button.pack(side="right")
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="right", padx=6)

        bar = ttk.Frame(self.root, padding=(14, 5))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status, style="Hint.TLabel").pack(side="left")

    def text_panel(self, parent, font):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        field = tk.Text(holder, bg=PANEL, fg=TEXT, font=font, width=42, relief="flat",
                        padx=10, pady=8, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(holder, command=field.yview)
        field.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        field.pack(fill="both", expand=True)
        return field

    def choose_workspace(self):
        if self.cancel:
            return
        folder = filedialog.askdirectory(parent=self.root, title="选择工作区")
        if folder:
            self.set_workspace(folder)

    def set_workspace(self, folder):
        self.workspace = Path(folder).resolve()
        self.history.clear()
        self.preview_path = None
        self.code_title.configure(text="代码预览")
        self.show_code("在左侧选择文本文件。")
        self.refresh_files()

    def choose_mcp(self):
        if self.cancel:
            return
        config = filedialog.askopenfilename(parent=self.root, title="选择可信的 MCP 配置文件",
                                            filetypes=[("JSON", "*.json")])
        if config:
            self.config = Path(config)
            self.status.set(f"MCP 配置：{self.config.name}")

    def settings(self):
        if self.cancel:
            return
        value = simpledialog.askstring("DeepSeek 设置", "DeepSeek API Key（仅本次运行保留）",
                                       show="•", parent=self.root)
        if value is not None:
            self.key = value.strip()
            self.status.set("API Key 已设置" if self.key else "API Key 已清空")

    def refresh_files(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.paths = {}
        if not self.workspace:
            return
        self.location.set(f"工作区 / {self.workspace.name}")
        self.insert_files("", self.workspace)

    def insert_files(self, parent, folder):
        try:
            items = sorted(folder.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
            for path in items[:300]:
                if path.name.lower() in HIDDEN_NAMES or path.name.startswith(".env."):
                    continue
                if not path.resolve().is_relative_to(self.workspace):
                    continue
                item = self.tree.insert(parent, "end", text=path.name)
                self.paths[item] = path
                if path.is_dir():
                    self.tree.insert(item, "end", text="展开…")
        except OSError as error:
            self.status.set(str(error))

    def expand_folder(self, _event):
        item = self.tree.focus()
        children = self.tree.get_children(item)
        if len(children) == 1 and children[0] not in self.paths:
            self.tree.delete(children[0])
            self.insert_files(item, self.paths[item])

    def select_file(self, _event=None):
        selection = self.tree.selection()
        path = self.paths.get(selection[0]) if selection else None
        if path and path.is_file():
            self.preview_path = path
            self.preview_offset = 1
            self.preview()

    def next_page(self):
        if self.preview_path:
            self.preview_offset += 100
            self.preview()

    def preview(self):
        self.code_title.configure(text=self.preview_path.name)
        try:
            value = read_file(str(self.preview_path), self.preview_offset, 100, workspace=self.workspace)
            if isinstance(value, dict):
                value = f"图片文件 · {value['mime_type']}"
            self.show_code(value[:30000])
        except (OSError, ValueError) as error:
            self.show_code(str(error))

    def show_code(self, text):
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("end", text)
        self.code.configure(state="disabled")

    def append(self, text, tag):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def send(self):
        if self.cancel:
            return
        prompt = self.prompt.get("1.0", "end").strip()
        if not prompt:
            return
        clean = remove_prompt_keys(prompt, self.key)
        if clean != prompt:
            self.prompt.delete("1.0", "end")
            self.prompt.insert("1.0", clean.strip())
            messagebox.showwarning("请在设置中输入密钥", PROMPT_KEY_NOTICE, parent=self.root)
            return
        if not self.workspace:
            messagebox.showinfo("工作区", "请先选择一个项目目录。", parent=self.root)
            return
        if not self.key:
            self.settings()
            if not self.key:
                return
        self.prompt.delete("1.0", "end")
        self.start(prompt)

    def demo(self):
        if self.cancel:
            return
        workspace = tempfile.mkdtemp(prefix="mini-cursor-demo-")
        demo_fixture(workspace)
        self.set_workspace(workspace)
        self.start("修复 average 的空列表报错，运行测试并调用 MCP 检查清单。", demo=True)

    def start(self, prompt, demo=False):
        self.cancel = threading.Event()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.shell_check.configure(state="disabled")
        self.status.set("运行中")
        self.append("你 / " + prompt, "answer")
        allowed = demo or self.allow_shell.get()
        config = self.config
        history = list(self.history)
        workspace = self.workspace
        cancel = self.cancel
        key = self.key

        def run():
            try:
                agent = Agent(workspace, self.events.put, cancel, key=key, model=self.model,
                              allow_shell=allowed, config=config)
                answer = agent.run(prompt, history, demo=demo)
                self.events.put({"kind": "done", "text": "已完成",
                                 "history": [] if demo else [
                                     {"role": "user", "content": prompt},
                                     {"role": "assistant", "content": answer},
                                 ]})
            except Cancelled:
                self.events.put({"kind": "done", "text": "已停止"})
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
                text = str(error).replace(key, "[密钥已隐藏]") if key else str(error)
                self.events.put({"kind": "error", "text": text})
                self.events.put({"kind": "done", "text": "运行失败"})

        threading.Thread(target=run, daemon=True).start()

    def start_durable(self):
        if self.cancel:
            return
        if not self.workspace:
            messagebox.showinfo("工作区", "请先选择一个项目目录。", parent=self.root)
            return
        workspace = self.workspace.resolve()
        state = (workspace / ".mini-cursor" / "workspace-check.json").resolve()
        if not state.is_relative_to(workspace):
            messagebox.showerror("续跑检查", "检查点必须在工作区内。", parent=self.root)
            return
        signal = self.cancel = threading.Event()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.shell_check.configure(state="disabled")
        self.status.set("正在检查工作区")

        def run():
            try:
                run_workflow(workspace, state, self.events.put, cancel=signal)
                text = "检查已完成"
            except Cancelled as error:
                text = str(error)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
                self.events.put({"kind": "error", "text": str(error)})
                text = "检查失败"
            self.events.put({"kind": "done", "text": text})

        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        if self.cancel:
            self.cancel.set()
            self.status.set("正在停止…")

    def poll(self):
        labels = {"call": "调用", "error": "失败", "diff": "代码差异", "mcp": "MCP", "skill": "Skill", "rules": "项目规则", "denied": "Hook 拒绝",
                  "autotest": "自动测试", "reviewer": "只读审查",
                  "step": "检查步骤", "resume": "恢复", "notification": "完成通知",
                  "already_complete": "检查结果",
                  "result": "结果", "status": "状态", "answer": "DeepSeek"}
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event["kind"]
            if kind == "done":
                self.history.extend(event.get("history", []))
                self.history = self.history[-24:]
                self.cancel = None
                self.send_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.shell_check.configure(state="normal")
                self.status.set(event["text"])
                self.append(event["text"], "status")
                self.refresh_files()
                if self.preview_path:
                    self.preview()
            else:
                title = "离线演示结果" if event.get("demo") else labels.get(kind, kind)
                if event.get("name"):
                    title += f" / {event['name']}"
                tag = "error" if kind == "denied" or (kind == "autotest" and not event["passed"]) else kind
                self.append(f"{title}\n{event['text']}", tag)
                if kind == "notification":
                    messagebox.showinfo("Mini Cursor 完成通知", event["text"], parent=self.root)
        self.root.after(65, self.poll)

    def close(self):
        if self.cancel:
            self.stop()
            self.root.after(100, self.close)
        else:
            self.root.destroy()


def inspect(tokenizer_path=None):
    from skills_inspect import print_report

    from app.inspect import tokenizer_file

    print_report(tokenizer_path or tokenizer_file())


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--durable-check":
        if sys.stdout is None:
            sys.stdout = io.TextIOWrapper(pipe(None, -11, "wb"), encoding="utf-8", write_through=True)

        def emit(event):
            print(json.dumps(event), flush=True)

        run_workflow(Path(sys.argv[2]), Path(sys.argv[3]), emit)
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--skill-script":
        name = sys.argv[2]
        if name not in SCRIPTS:
            raise SystemExit("未知的技能脚本")
        for attr, descriptor in (("stdout", -11), ("stderr", -12)):
            if getattr(sys, attr) is None:
                stream = io.TextIOWrapper(pipe(None, descriptor, "wb"), encoding="utf-8", write_through=True)
                setattr(sys, attr, stream)
        del sys.argv[1:3]
        runpy.run_path(str(skill_script_path(name)), run_name="__main__")
        return
    if "--mcp-demo" in sys.argv:
        serve_demo_mcp()
        return
    if "--demo-tests" in sys.argv:
        if sys.stderr is None:
            sys.stderr = io.TextIOWrapper(pipe(None, -12, "wb"), encoding="utf-8", write_through=True)
        suite = unittest.defaultTestLoader.discover(str(Path.cwd()))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() and result.testsRun else 1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--inspect", action="store_true", help="生成 Skill 验收报告")
    parser.add_argument("--tokenizer", type=Path, help="验收使用的 tokenizer.json")
    args = parser.parse_args()
    if args.inspect:
        inspect(args.tokenizer)
        return
    root = tk.Tk()
    Desktop(root, args.workspace)
    root.mainloop()


if __name__ == "__main__":
    main()
