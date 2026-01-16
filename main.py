from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import time
import json
import os

# === 数据文件路径配置 ===
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(CURRENT_DIR, "simple_task_data.json")
EXPIRATION_SECONDS = 30 * 60  # 30分钟

@register("quick_task", "Squ1", "简易任务板：发布(覆盖)/列表/搜索", "1.1.1", "repo url")
class QuickTaskPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.tasks = []
        self.load_data()

    # === 内部工具函数 ===

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception:
                self.tasks = []
        else:
            self.tasks = []

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)

    def clean_expired(self):
        now = int(time.time())
        valid_tasks = [t for t in self.tasks if (now - t['create_time']) < EXPIRATION_SECONDS]
        if len(valid_tasks) != len(self.tasks):
            self.tasks = valid_tasks
            self.save_data()

    def _format_task_list(self, task_list):
        if not task_list:
            return "📭 当前没有符合条件的任务。"
        msg = []
        now = int(time.time())
        for t in task_list:
            elapsed = int((now - t['create_time']) / 60)
            elapsed_str = f"{elapsed}分钟前" if elapsed > 0 else "刚刚"
            msg.append(f"➖➖➖➖➖➖➖")
            msg.append(f"📝 {t['content']}")
            msg.append(f"👤 {t['publisher']} | 🕒 发布于 {elapsed_str}")
        return "\n".join(msg)

    def _strip_prefix(self, message: str, aliases: list) -> str:
        """智能移除指令前缀"""
        message = message.strip()
        # 按长度倒序排列，防止"发布任务"被误识别为"发布"
        sorted_aliases = sorted(aliases, key=len, reverse=True)
        for alias in sorted_aliases:
            if message.lower().startswith(alias.lower()):
                return message[len(alias):].strip()
        return message

    # === 指令处理函数 ===

    # 1. 帮助指令
    @filter.command("任务帮助", alias=["taskhelp", "help task"])
    async def task_help(self, event: AstrMessageEvent):
        '''显示任务板帮助'''
        msg = (
            "📋 **任务板使用说明**\n"
            "1. **发布/pub <内容>**\n"
            "   (自动覆盖旧任务，30分钟过期)\n"
            "2. **删除/del**\n"
            "3. **列表/ls**\n"
            "4. **搜索/find <关键词>**"
        )
        yield event.plain_result(msg)

    # 2. 发布指令
    @filter.command("发布任务", alias=["发布", "pub", "task"])
    async def publish_task(self, event: AstrMessageEvent):
        '''发布新任务 (自动覆盖)'''
        user_name = event.get_sender_name()
        user_id = event.get_sender_id()

        # 定义当前指令的所有前缀，用于解析
        aliases = ["发布任务", "发布", "pub", "task"]
        content = self._strip_prefix(event.message_str, aliases)

        if not content:
            yield event.plain_result("❌ 内容不能为空，例如：pub 求带副本")
            return

        self.clean_expired()

        # 覆盖逻辑
        overwritten = False
        original_count = len(self.tasks)
        self.tasks = [t for t in self.tasks if t['publisher_id'] != user_id]

        if len(self.tasks) < original_count:
            overwritten = True

        new_task = {
            "content": content,
            "publisher": user_name,
            "publisher_id": user_id,
            "create_time": int(time.time())
        }
        self.tasks.append(new_task)
        self.save_data()

        logger.info(f"User {user_name} published a task.")

        msg = f"✅ 任务已发布 (30分钟过期)\n📝 {content}"
        if overwritten:
            msg = f"🔄 旧任务已覆盖！\n" + msg

        yield event.plain_result(msg)

    # 3. 删除指令
    @filter.command("删除任务", alias=["撤销任务", "del", "rm", "删除"])
    async def delete_task(self, event: AstrMessageEvent):
        '''删除自己的任务'''
        user_id = event.get_sender_id()
        self.clean_expired()

        target = None
        for t in self.tasks:
            if t['publisher_id'] == user_id:
                target = t
                break

        if target:
            self.tasks.remove(target)
            self.save_data()
            yield event.plain_result(f"🗑️ 已删除你的任务：\n“{target['content']}”")
        else:
            yield event.plain_result("❌ 你当前没有发布的任务")

    # 4. 列表指令
    @filter.command("任务列表", alias=["列表", "ls", "tasks", "活"])
    async def list_tasks(self, event: AstrMessageEvent):
        '''查看所有任务'''
        self.clean_expired()
        if not self.tasks:
            yield event.plain_result("📭 任务板是空的")
            return

        header = "📋 **实时任务板 (30分钟过期)**\n"
        body = self._format_task_list(self.tasks)
        yield event.plain_result(header + body)

    # 5. 搜索指令
    @filter.command("搜索任务", alias=["搜索", "find", "query"])
    async def search_task(self, event: AstrMessageEvent):
        '''搜索任务'''
        aliases = ["搜索任务", "搜索", "find", "query"]
        keyword = self._strip_prefix(event.message_str, aliases)

        self.clean_expired()

        if not keyword:
            # 这里的逻辑是：如果没有关键词，就显示全部列表
            if not self.tasks:
                yield event.plain_result("📭 任务板是空的")
            else:
                yield event.plain_result("📋 **所有任务**\n" + self._format_task_list(self.tasks))
            return

        matched = [t for t in self.tasks if keyword in t['content']]
        yield event.plain_result(f"🔍 **“{keyword}”搜索结果**\n" + self._format_task_list(matched))