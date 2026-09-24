from _paths import ROOT, SERVER  # noqa
import tempfile
import unittest
from pathlib import Path
import sessions


class ProtocolTests(unittest.TestCase):
    def test_durable_commit_and_answer_request(self):
        self.assertTrue((SERVER / 'voice_turn_protocol.py').exists(), 'voice protocol exists')
        import voice_turn_protocol as vp
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'test.db'
            store = sessions.SessionStore(db)
            sid = store.get_or_create(None, brain='brain', engine='test', model='test')
            mid=store.append_message(sid, 'assistant', 'Thời gian chờ là khoảng nghỉ trước khi gửi câu nói.')
            vp.note_answer(store,mid,'Thời gian chờ là khoảng nghỉ trước khi gửi câu nói.')
            receipt = vp.commit(store, sid, 'u1', 'Vâng anh hiểu rồi', 'ack_only')
            self.assertEqual(receipt['response_policy'], 'ack_only')
            self.assertTrue(receipt['created'])
            self.assertEqual(vp.commit(store, sid, 'u1', 'Vâng anh hiểu rồi', 'ack_only')['created'], False)
            self.assertEqual(len(store.get_messages(sid)), 2)
            self.assertEqual(vp.request_answer(store, sid, receipt['message_id'])['content'], 'Vâng anh hiểu rồi')
            self.assertIsNone(vp.request_answer(store, sid, receipt['message_id']))
            self.assertIsNone(vp.request_answer(store, 'wrong-session', receipt['message_id']))
            reopened = sessions.SessionStore(db)
            self.assertFalse(vp.commit(reopened, sid, 'u1', 'Vâng anh hiểu rồi', 'auto')['created'])
            with self.assertRaises(ValueError):
                vp.commit(reopened, sid, 'u1', 'changed transcript', 'auto')
            store._conn.close(); reopened._conn.close()

    def test_unknown_questions_and_actions_never_ack(self):
        self.assertTrue((SERVER / 'voice_turn_protocol.py').exists())
        import voice_turn_protocol as vp
        with tempfile.TemporaryDirectory() as d:
            store = sessions.SessionStore(Path(d) / 'test.db')
            for previous in ['', 'Anh có muốn xóa không?', 'Hãy xác nhận để em thực hiện.', 'Thời gian chờ là 1 giây. Anh muốn đổi không', 'Thời gian chờ là 10 giây. Anh có cần em đổi thành 20 giây không', 'Vâng, em đã chuẩn bị thao tác.']:
                sid = store.get_or_create(None, brain='brain', engine='test', model='test')
                if previous:
                    mid=store.append_message(sid, 'assistant', previous)
                    vp.note_answer(store,mid,previous)
                self.assertEqual(vp.commit(store,sid,'u','Vâng anh hiểu rồi','ack_only')['response_policy'],'auto',previous)
            sid = store.get_or_create(None, brain='brain', engine='test', model='test')
            store.append_message(sid,'assistant','Thời gian chờ là một khoảng nghỉ.')
            self.assertEqual(vp.commit(store,sid,'u','Vâng nhưng kiểm tra lại giúp anh','ack_only')['response_policy'],'auto')
            store._conn.close()

if __name__ == '__main__': unittest.main()
