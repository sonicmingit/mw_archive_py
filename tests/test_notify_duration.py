import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from notification_templates import build_alert_notification, build_success_notification
from tg_push import TelegramPushService
from feishu_push import FeishuPushService


class _DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class NotifyDurationTest(unittest.TestCase):
    def test_success_template_includes_duration_and_missing_count(self):
        rendered = build_success_notification({
            'title': '测试模型',
            'base_name': 'MW_1_test',
            'online_url': 'http://127.0.0.1:8000/v2/files/MW_1_test',
            'duration_text': '1分5秒',
            'missing_count': 2,
        })
        self.assertEqual(rendered['title'], '✅ 模型归档成功')
        self.assertIn('耗时：1分5秒', rendered['body'])
        self.assertIn('缺失 3MF：2', rendered['body'])

    def test_alert_template_merges_summary_and_lines(self):
        rendered = build_alert_notification({
            'icon': '⚠️',
            'title': 'Cookie 即将过期',
            'summary': '请尽快更新 Cookie。',
            'lines': ['当前仅剩 1 组可用', '建议立即检查登录状态'],
        })
        self.assertEqual(rendered['title'], '⚠️ Cookie 即将过期')
        self.assertIn('请尽快更新 Cookie。', rendered['body'])
        self.assertIn('当前仅剩 1 组可用', rendered['body'])

    def test_telegram_success_text_includes_duration(self):
        svc = TelegramPushService(
            cfg_getter=lambda: {},
            logger=_DummyLogger(),
            on_archive_url=lambda url: {},
            on_cookie_status=lambda: '',
            on_count=lambda: '',
            on_search=lambda q: '',
            on_get_base_url=lambda: '',
            on_set_base_url=lambda raw: '',
            on_redownload_missing=lambda: '',
        )
        text = svc._format_success_text({
            'title': '测试模型',
            'base_name': 'MW_1_test',
            'online_url': 'http://127.0.0.1:8000/v2/files/MW_1_test',
            'duration_text': '1分5秒',
        })
        self.assertIn('耗时', text)
        self.assertIn('1分5秒', text)

    def test_feishu_success_text_includes_duration(self):
        svc = FeishuPushService(cfg_getter=lambda: {}, logger=_DummyLogger())
        text = svc._format_success_text({
            'title': '测试模型',
            'base_name': 'MW_1_test',
            'online_url': 'http://127.0.0.1:8000/v2/files/MW_1_test',
            'duration_text': '1分5秒',
        })
        self.assertIn('耗时', text)
        self.assertIn('1分5秒', text)

    def test_telegram_and_feishu_share_same_success_text(self):
        payload = {
            'title': '测试模型',
            'base_name': 'MW_1_test',
            'online_url': 'http://127.0.0.1:8000/v2/files/MW_1_test',
            'duration_text': '1分5秒',
            'missing_count': 1,
        }
        tg = TelegramPushService(
            cfg_getter=lambda: {},
            logger=_DummyLogger(),
            on_archive_url=lambda url: {},
            on_cookie_status=lambda: '',
            on_count=lambda: '',
            on_search=lambda q: '',
            on_get_base_url=lambda: '',
            on_set_base_url=lambda raw: '',
            on_redownload_missing=lambda: '',
        )
        fs = FeishuPushService(cfg_getter=lambda: {}, logger=_DummyLogger())
        self.assertEqual(tg._format_success_text(payload), fs._format_success_text(payload))


if __name__ == '__main__':
    unittest.main()
